default: sandbox libsandbox.so

sandbox: sandbox.c
	gcc -Wall -O2 -o sandbox sandbox.c

libsandbox.so: libsandbox.c
	gcc -Wall -O2 -ldl --shared -o libsandbox.so libsandbox.c

clean:
	rm sandbox
	rm libsandbox.so
