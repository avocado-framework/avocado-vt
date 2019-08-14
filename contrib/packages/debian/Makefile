PROJECT=avocado

all:
	@echo
	@echo "Debian related targets:"
	@echo "deb:      Generate both source and binary debian packages"
	@echo "deb-src:  Generate a source debian package"
	@echo "deb-bin:  Generate a binary debian package"
	@echo

prepare-source:
	# build the source package in the parent directory
	# then rename it to project_version.orig.tar.gz
	dch -D "bionic" -M -v "$(VERSION)" "Automated (make builddeb) build."
	$(PYTHON) setup.py sdist $(COMPILE) --dist-dir=../ --prune
	rename -f 's/$(PROJECT)-(.*)\.tar\.gz/$(PROJECT)_$$1\.orig\.tar\.gz/' ../*

deb-src: prepare-source
	# build the source package
	dpkg-buildpackage -S -elookkas@gmail.com -rfakeroot

deb-bin: prepare-source
	# build binary package
	dpkg-buildpackage -b -rfakeroot

deb: prepare-source
	# build both source and binary packages
	dpkg-buildpackage -i -I -rfakeroot
