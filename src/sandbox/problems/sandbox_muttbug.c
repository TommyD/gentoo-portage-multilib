#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(int argc, char *argv[])
{
	FILE *fd ;
	
	printf("unlink\n");
	unlink("/tmp/test");
	printf("... done\n");
	
	printf("fopen\n");
	fd = fopen("/tmp/test", "a+");
	printf("... done\n");
	
	printf("fputc\n");
	fputc('7', fd);
	printf("... done\n");
	
	printf("fseek\n");
	fseek(fd, 0, SEEK_SET);
	printf("... done\n");
	
	printf("freopen\n");
	fd = freopen("/tmp/test", "r", fd);
	printf("... done\n");
	
	printf("fgetc ");
	printf("%c\n", fgetc(fd));
	printf("... done\n");
	
	printf("fseek\n");
	fseek(fd, 0, SEEK_SET);
	printf("... done\n");
	
	printf("fclose\n");
	fclose(fd);
        printf("... done\n");
        return 0;
}
