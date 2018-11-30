all: sort

clean:
	rm -rv build dist

sort: sort.exe

%.exe: %.py
	pyinstaller $< -F -w