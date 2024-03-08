import concurrent.futures
import re

from pathlib import Path

from bs4 import BeautifulSoup, Comment
from markdownify import markdownify
from tclogger import logger
from termcolor import colored

from constants import IGNORE_TAGS, IGNORE_CLASSES


class HTMLPurifier:
    def __init__(self, verbose=False, output_format="markdown", keep_href=False):
        self.verbose = verbose
        self.output_format = output_format
        self.keep_href = keep_href

    def html_to_markdown(self, html_str):
        markdown_str = markdownify(
            html_str, strip=["a"], wrap_width=120, heading_style="ATX"
        )
        self.markdown_str = re.sub(r"\n{3,}", "\n\n", markdown_str)

        return self.markdown_str

    def filter_elements(self, html_str):
        soup = BeautifulSoup(html_str, "html.parser")

        # Remove comments
        comments = soup.find_all(string=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment.extract()

        # Remove elements containing patterns to ignore
        removed_element_counts = 0
        for element in soup.find_all():
            try:
                class_attr = element.get("class", [])
                class_str = " ".join(list(class_attr))
            except:
                class_str = ""

            try:
                id_str = element.get("id", "")
            except:
                id_str = ""

            class_id_str = f"{class_str} {id_str}"

            is_class_in_ignore_classes = any(
                re.search(ignore_class, class_id_str, flags=re.IGNORECASE)
                for ignore_class in IGNORE_CLASSES
            )
            is_element_in_ignore_tags = element.name in IGNORE_TAGS

            # check if this element has no text
            is_no_text = (
                not element.get_text().strip()
                # exclude img
                # and not element.find_all("img")
                # and not element.name == "img"
            )

            if is_element_in_ignore_tags or is_class_in_ignore_classes or is_no_text:
                element.extract()
                removed_element_counts += 1

        logger.mesg(
            f"  - Elements: "
            f'{colored(len(soup.find_all()),"light_green")} (Remained) '
            f'/ {colored(removed_element_counts,"light_red")} (Removed)'
        )

        return str(soup)

    def filter_attrs(self, html_str):
        soup = BeautifulSoup(html_str, "html.parser")
        for element in soup.find_all():
            if element.name == "a":
                if self.keep_href:
                    element.attrs = {"href": element.get("href")}
                else:
                    element.attrs = {}
            elif element.name == "img":
                element.attrs = {"alt": element.get("alt") or None}
                if self.keep_href:
                    element["src"] = element.get("src")
                else:
                    element.attrs = {}
            else:
                element.attrs = {}

        return str(soup)

    def read_html_file(self, html_path):
        logger.note(f"> Purifying content in: {html_path}")

        if not Path(html_path).exists():
            warn_msg = f"File not found: {html_path}"
            logger.warn(warn_msg)
            raise FileNotFoundError(warn_msg)

        encodings = ["utf-8", "latin-1"]
        for encoding in encodings:
            try:
                with open(html_path, "r", encoding=encoding, errors="ignore") as rf:
                    html_str = rf.read()
                    return html_str
            except UnicodeDecodeError:
                pass
        else:
            warn_msg = f"No matching encodings: {html_path}"
            logger.warn(warn_msg)
            raise UnicodeDecodeError(warn_msg)

    def purify_file(self, html_path, filter_elements=True, save=True, output_path=None):
        logger.enter_quiet(not self.verbose)
        html_str = self.read_html_file(html_path)
        if not html_str:
            return {"path": html_path, "output_path": None, "output": ""}
        else:
            result = self.purify_str(html_str, filter_elements=filter_elements)
        if save:
            if not output_path:
                if self.output_format == "html":
                    output_path = Path(str(html_path) + ".pure")
                else:
                    output_path = Path(html_path.with_suffix(f".{self.output_format}"))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as wf:
                wf.write(result)
            logger.success(f"  > Saved to: {output_path}")
        logger.exit_quiet(not self.verbose)
        return {"path": html_path, "output_path": output_path, "output": result}

    def purify_str(self, html_str, filter_elements=True):
        logger.enter_quiet(not self.verbose)
        if not html_str:
            return ""

        if filter_elements:
            html_str = self.filter_elements(html_str)

        if self.output_format == "markdown":
            markdown_str = self.html_to_markdown(html_str)
            result = markdown_str.strip()
        else:
            html_str = self.filter_attrs(html_str)
            result = html_str.strip()

        logger.exit_quiet(not self.verbose)
        return result


class BatchHTMLPurifier:
    def __init__(self, verbose=False, output_format="markdown", keep_href=False):
        self.html_path_and_purified_content_list = []
        self.done_count = 0
        self.verbose = verbose
        self.output_format = output_format
        self.keep_href = keep_href

    def purify_single_html_file(self, html_path):
        purifier = HTMLPurifier(
            verbose=self.verbose,
            output_format=self.output_format,
            keep_href=self.keep_href,
        )
        result = purifier.purify_file(html_path)
        self.html_path_and_purified_content_list.append(
            {
                "path": html_path,
                "output": result["output"],
                "output_path": result["output_path"],
                "format": self.output_format,
            }
        )
        self.done_count += 1

        if self.verbose:
            logger.success(
                f"> Purified [{self.done_count}/{self.total_count}]: [{html_path}]"
            )

    def purify_files(self, html_paths):
        self.html_path = html_paths
        self.total_count = len(self.html_path)
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(self.purify_single_html_file, html_path)
                for html_path in self.html_path
            ]
            for idx, future in enumerate(concurrent.futures.as_completed(futures)):
                result = future.result()

        return self.html_path_and_purified_content_list


def purify_html_file(
    html_path, verbose=False, output_format="markdown", keep_href=False
):
    purifier = HTMLPurifier(
        verbose=verbose, output_format=output_format, keep_href=keep_href
    )
    return purifier.purify_file(html_path)


def purify_html_str(html_str, verbose=False, output_format="markdown", keep_href=False):
    purifier = HTMLPurifier(
        verbose=verbose, output_format=output_format, keep_href=keep_href
    )
    return purifier.purify_str(html_str)


def purify_html_files(
    html_paths, verbose=False, output_format="markdown", keep_href=False
):
    batch_purifier = BatchHTMLPurifier(
        verbose=verbose, output_format=output_format, keep_href=keep_href
    )
    return batch_purifier.purify_files(html_paths)


if __name__ == "__main__":
    html_root = Path(__file__).parent / "samples"
    html_paths = list(html_root.glob("*.html"))
    html_path_and_purified_content_list = purify_html_files(
        html_paths, verbose=False, output_format="html", keep_href=False
    )
    for item in html_path_and_purified_content_list:
        html_path = item["path"]
        purified_content = item["output"]
        output_path = item["output_path"]
        # logger.line(purified_content)
        # logger.file(html_path)
        logger.file(output_path.name)