#!/usr/bin/env python3
"""Render README.md to a PDF with line numbers in the left margin."""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def get_git_info(repo_dir: Path) -> str:
  """Return a string with the last commit hash, date/time, and local edit status."""
  try:
    commit_info = subprocess.run(
        ["git", "log", "-1", "--format=%h (%ci)"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status_out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    header = f"Last commit: \\texttt{{{commit_info}}}"
    if status_out:
      header += " (contains local edits)"
    return header
  except (subprocess.CalledProcessError, FileNotFoundError):
    return ""


def parse_img_latex(
    src: str, style: str = "", width_attr: str = "", base_dir: Path | None = None
) -> str:
  """Convert an image reference and optional sizing into LaTeX code."""
  img_path = Path(src)
  if base_dir is not None and not img_path.is_absolute():
    img_path = (base_dir / img_path).resolve()

  width_spec = r"width=\linewidth"
  m_style_w = re.search(r"(?:^|;)\s*width\s*:\s*([^;]+)", style, re.I)
  raw_w = m_style_w.group(1).strip() if m_style_w else width_attr.strip()
  if raw_w:
    if raw_w.endswith("%"):
      try:
        frac = float(raw_w[:-1].strip()) / 100.0
        width_spec = f"width={frac:.4f}\\linewidth, max width=\\linewidth"
      except ValueError:
        pass
    elif re.match(r"^\d+(\.\d+)?\s*(in|cm|mm|pt|em|ex)$", raw_w, re.I):
      clean_w = re.sub(r"\s+", "", raw_w.lower())
      width_spec = f"width={clean_w}, max width=\\linewidth"
    elif re.match(r"^\d+(\.\d+)?\s*(px)?$", raw_w, re.I):
      val_in = float(re.sub(r"px$", "", raw_w.strip(), flags=re.I)) / 96.0
      width_spec = f"width={val_in:.4f}in, max width=\\linewidth"

  return (
      "\\begin{nolinenumbers}\n"
      "\\begin{center}\n"
      f"\\includegraphics[{width_spec}]{{{img_path.as_posix()}}}\n"
      "\\end{center}\n"
      "\\end{nolinenumbers}"
  )


def md_to_latex(
    md_text: str, git_header: str = "", base_dir: Path | None = None
) -> str:
  """Convert the article Markdown (with LaTeX math) into a LaTeX document."""

  def repl_display_math(match: re.Match[str]) -> str:
    inner = match.group(1).strip()
    return (
        "\\begin{linenomathWithnumbers}\n\\[\n"
        f"{inner}\n"
        "\\]\n\\end{linenomathWithnumbers}"
    )

  text = re.sub(r"\$\$(.*?)\$\$", repl_display_math, md_text, flags=re.S)

  lines = text.splitlines()
  out_lines = []
  in_list = False
  in_math_block = False

  def format_inline(s: str) -> str:
    # Split by inline math $...$ so math contents are preserved untouched.
    parts = re.split(r"(\$[^\$]+\$)", s)
    res = []
    for part in parts:
      if part.startswith("$") and part.endswith("$"):
        res.append(part)
      else:
        p = part.replace("%", r"\%")
        p = p.replace("²", "$^2$")
        p = p.replace("“", "``").replace("”", "''")
        p = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", p)
        p = re.sub(r"\*(.+?)\*", r"\\textit{\1}", p)
        res.append(p)
    return "".join(res)

  for line in lines:
    if line.strip() == r"\begin{linenomathWithnumbers}":
      if in_list:
        out_lines.append(r"\end{itemize}")
        in_list = False
      in_math_block = True
      out_lines.append(line)
      continue
    if in_math_block:
      out_lines.append(line)
      if line.strip() == r"\end{linenomathWithnumbers}":
        in_math_block = False
      continue

    m_h1 = re.match(r"^#\s+(.+)$", line)
    m_h2 = re.match(r"^##\s+(.+)$", line)
    m_h3 = re.match(r"^###\s+(.+)$", line)
    m_li = re.match(r"^-\s+(.+)$", line)
    m_html_img = re.match(r"^\s*<img\b([^>]*)/?>\s*$", line, flags=re.I)
    m_md_img = re.match(r"^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$", line)

    if m_h1:
      if in_list:
        out_lines.append(r"\end{itemize}")
        in_list = False
      out_lines.append(f"\\section{{{format_inline(m_h1.group(1).strip())}}}")
    elif m_h2:
      if in_list:
        out_lines.append(r"\end{itemize}")
        in_list = False
      out_lines.append(
          f"\\subsection{{{format_inline(m_h2.group(1).strip())}}}"
      )
    elif m_h3:
      if in_list:
        out_lines.append(r"\end{itemize}")
        in_list = False
      out_lines.append(
          f"\\subsubsection{{{format_inline(m_h3.group(1).strip())}}}"
      )
    elif m_html_img:
      if in_list:
        out_lines.append(r"\end{itemize}")
        in_list = False
      attrs = m_html_img.group(1)
      m_src = re.search(r'src\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
      m_style = re.search(r'style\s*=\s*["\']([^"\']*)["\']', attrs, re.I)
      m_width = re.search(
          r'(?<![\w-])width\s*=\s*["\']([^"\']*)["\']', attrs, re.I
      )
      if m_src:
        out_lines.append(
            parse_img_latex(
                m_src.group(1),
                style=m_style.group(1) if m_style else "",
                width_attr=m_width.group(1) if m_width else "",
                base_dir=base_dir,
            )
        )
      else:
        out_lines.append(format_inline(line))
    elif m_md_img:
      if in_list:
        out_lines.append(r"\end{itemize}")
        in_list = False
      out_lines.append(
          parse_img_latex(m_md_img.group(2).strip(), base_dir=base_dir)
      )
    elif m_li:
      if not in_list:
        out_lines.append(r"\begin{itemize}")
        in_list = True
      out_lines.append(f"  \\item {format_inline(m_li.group(1).strip())}")
    else:
      if in_list and line.strip() == "":
        out_lines.append(r"\end{itemize}")
        in_list = False
      out_lines.append(format_inline(line))

  if in_list:
    out_lines.append(r"\end{itemize}")

  body = "\n".join(out_lines)

  header_block = ""
  if git_header:
    header_block = (
        "\\begin{nolinenumbers}\n"
        f"\\noindent{{\\small\\sffamily\\textcolor{{gray!80!black}}{{{git_header}}}}}\n"
        "\\vspace{0.4em}\n"
        "\\hrule\n"
        "\\vspace{0.8em}\n"
        "\\end{nolinenumbers}\n"
    )

  return (
      r"""\documentclass[11pt]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage{microtype}
\usepackage[letterpaper, margin=1in, left=1.25in]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage[export]{adjustbox}
\usepackage{xcolor}
\usepackage[running, mathlines]{lineno}
\usepackage{parskip}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}

\setlist[itemize]{noitemsep, topsep=2pt}
\renewcommand\linenumberfont{\normalfont\footnotesize\sffamily\textcolor{gray!80!black}}
\setlength\linenumbersep{18pt}

\begin{document}
"""
      + header_block
      + "\\linenumbers\n"
      + body
      + "\n\\end{document}\n"
  )


def render_pdf(input_md: Path, output_pdf: Path) -> None:
  base_dir = input_md.resolve().parent
  git_header = get_git_info(base_dir)
  latex_src = md_to_latex(
      input_md.read_text(encoding="utf-8"), git_header, base_dir=base_dir
  )
  with tempfile.TemporaryDirectory() as tmpdir:
    tmp_path = Path(tmpdir)
    tex_file = tmp_path / "document.tex"
    tex_file.write_text(latex_src, encoding="utf-8")
    for _ in range(2):
      subprocess.run(
          [
              "pdflatex",
              "-interaction=nonstopmode",
              "-halt-on-error",
              tex_file.name,
          ],
          cwd=tmp_path,
          check=True,
          stdout=subprocess.DEVNULL,
      )
    shutil.copy2(tmp_path / "document.pdf", output_pdf)


def main() -> None:
  default_dir = Path(__file__).resolve().parent
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      "-i",
      "--input",
      type=Path,
      default=default_dir / "README.md",
      help="Input Markdown file (default: README.md)",
  )
  parser.add_argument(
      "-o",
      "--output",
      type=Path,
      default=default_dir / "README.pdf",
      help="Output PDF file (default: README.pdf)",
  )
  args = parser.parse_args()
  render_pdf(args.input, args.output)
  print(f"Wrote {args.output}")


if __name__ == "__main__":
  main()
