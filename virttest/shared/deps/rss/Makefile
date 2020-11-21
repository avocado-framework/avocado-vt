all:
	make rss.exe rss_amd64.exe finish.exe
rss.exe:
	i686-w64-mingw32-g++ rss.cpp -O2 -static-libgcc -lws2_32 -lshlwapi -mwindows -o rss.exe
rss_amd64.exe:
	x86_64-w64-mingw32-g++ rss.cpp -O2 -static-libgcc -lws2_32 -lshlwapi -mwindows -o rss_amd64.exe
finish.exe:
	i686-w64-mingw32-g++ finish.cpp -O2 -lws2_32 -o finish.exe
clean:
	rm -rf rss.exe rss_amd64.exe finish.exe
