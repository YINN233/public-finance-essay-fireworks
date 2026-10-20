# 编译：make          （XeLaTeX，两遍以稳定交叉引用）
# 清理：make clean
LATEX = xelatex -interaction=nonstopmode -halt-on-error
SRC   = main.tex preamble.tex $(wildcard sections/*.tex) $(wildcard appendix/*.tex)

all: main.pdf

main.pdf: $(SRC)
	$(LATEX) main.tex
	$(LATEX) main.tex

clean:
	rm -f main.pdf main.aux main.log main.out main.toc main.lof main.lot main.fls main.fdb_latexmk main.synctex.gz

.PHONY: all clean
