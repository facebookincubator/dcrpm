USE_BUILD=0
USE_LEGACY=0

black: dcrpm/*.py tests/*.py
	black $?

check-release: dist
	twine check dist/*

dist: dcrpm/*.py
ifeq ($(USE_BUILD), 1)
	python -m build
else
ifeq ($(USE_LEGACY), 1)
	python legacy_setup.py sdist bdist_wheel --universal
else
	python setup.py sdist bdist_wheel --universal
endif
endif

clean:
	rm -rf build dist dcrpm.egg-info

install:
	pip install --force-reinstall dist/dcrpm*.whl

test:
	pytest -v
