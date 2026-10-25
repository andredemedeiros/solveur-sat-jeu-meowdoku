#!/usr/bin/env python3
"""Export du rapport : rapport.md -> rapport.html (pandoc) -> rapport.pdf
(impression par un navigateur Chromium sans interface : Edge ou Chrome).
Fonctionne sous Windows, Linux, macOS et WSL (Edge de Windows appelé depuis
Linux : chemins convertis par ``wslpath``).

    python rapport/build_pdf.py
"""
import os
import pathlib
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

PANDOC = [shutil.which("pandoc"), os.path.expandvars(r"%LOCALAPPDATA%\Pandoc\pandoc.exe")]
BROWSERS = [shutil.which("chromium"), shutil.which("google-chrome"), shutil.which("msedge"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]


def first(paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    sys.exit(f"introuvable : {paths}")


def browser_path(browser, path):
    """Chemin vu par le navigateur : Windows si c'est un .exe lancé depuis WSL."""
    if browser.startswith("/mnt/") and browser.endswith(".exe"):
        return subprocess.run(["wslpath", "-w", path], capture_output=True, text=True,
                              check=True).stdout.strip()
    return path


def main():
    md = os.path.join(HERE, "rapport.md")
    html = os.path.join(HERE, "rapport.html")
    pdf = os.path.join(HERE, "rapport.pdf")
    subprocess.run([first(PANDOC), md, "-s", "--mathml", "--embed-resources", "--resource-path", HERE,
                    "--css", os.path.join(HERE, "style.css"), "-o", html], check=True)
    browser = first(BROWSERS)
    win = browser_path(browser, html)
    uri = pathlib.Path(html).as_uri() if win == html else "file:///" + win.replace("\\", "/")
    subprocess.run([browser, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={browser_path(browser, pdf)}", uri], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("écrit :", pdf)


if __name__ == "__main__":
    main()
