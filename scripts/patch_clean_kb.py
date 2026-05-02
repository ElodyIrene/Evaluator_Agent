from pathlib import Path
import re

path = Path("scripts/clean_kb_html_to_md.py")

text = path.read_text(encoding="utf-8")

start = text.index("def remove_noise(soup: BeautifulSoup) -> None:")
end = text.index("\ndef choose_main_content", start)

new_function = '''def remove_noise(soup: BeautifulSoup) -> None:
    remove_tag_names = [
        "script",
        "style",
        "noscript",
        "svg",
        "canvas",
        "iframe",
        "form",
        "button",
        "input",
        "nav",
        "aside",
        "footer",
        "header",
    ]

    for tag_name in remove_tag_names:
        for tag in list(soup.find_all(tag_name)):
            if tag is not None:
                tag.decompose()

    noise_keywords = [
        "navbar",
        "sidebar",
        "footer",
        "header",
        "menu",
        "toc",
        "pagination",
        "breadcrumb",
        "search",
        "doc-sidebar",
        "table-of-contents",
    ]

    for tag in list(soup.find_all(True)):
        if tag is None:
            continue

        attrs = getattr(tag, "attrs", None)
        if not isinstance(attrs, dict):
            continue

        class_value = attrs.get("class", [])
        if isinstance(class_value, str):
            class_text = class_value
        elif isinstance(class_value, list):
            class_text = " ".join(str(item) for item in class_value)
        else:
            class_text = ""

        id_text = str(attrs.get("id", ""))

        combined = f"{class_text} {id_text}".lower()

        if any(keyword in combined for keyword in noise_keywords):
            tag.decompose()
'''

text = text[:start] + new_function + text[end:]

path.write_text(text, encoding="utf-8")

print("OK: remove_noise function patched")
