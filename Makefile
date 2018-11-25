all: sort rename

clean:
	rm -rv build dist

sort: sort.exe

rename: rename.exe

%.exe: %.py
	pyinstaller $< -F