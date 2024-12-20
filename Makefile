PYTHON=py

exec_targets=\
	sort.exe

all: exe

clean:
	$(RM) -r __pycache__
	$(RM) -r build
	$(RM) -r dist/
	$(RM) -r litedist/

exe: $(addprefix bin/,${exec_targets})

bin/%.exe: %.py
	mkdir -p bin
	${PYTHON} -m pip install -r requirements.txt
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