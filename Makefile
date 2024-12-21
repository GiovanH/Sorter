PYTHON=python3

exec_targets=\
	sort.exe

PY_SRCS=sort.py sbf.py contentcanvas.py filesystem.py win32_fileprops.py

all: exe

.PHONY: test
test:
	$(PYTHON) sort.py --base test

.PHONY: lint
lint: requirements
	-python3 -m mypy $(PY_SRCS)
	-vulture  $(PY_SRCS)

requirements: requirements.txt
	${PYTHON} -m pip install -r requirements.txt
	touch requirements

clean:
	$(RM) -r __pycache__
	$(RM) -r build
	$(RM) -r dist/
	$(RM) -r litedist/

exe: requirements $(addprefix bin/,${exec_targets})

bin/%.exe: %.py
	mkdir -p bin
	${PYTHON} -m pip install PyInstaller
	${PYTHON} -m PyInstaller \
		--onefile \
		--console \
		--distpath bin \
		--workpath build \
		--specpath build \
		--name $(notdir $@) \
		$<

.PHONY: all clean exe doc mods