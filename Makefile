black: dcrpm/*.py tests/*.py
	black $?

check-release: dist
	twine check dist/*

dist: dcrpm/*.py
	python -m build --sdist --wheel

clean:
	rm -rf build dist dcrpm.egg-info

install:
	pip install --force-reinstall dist/dcrpm*.whl

test:
	pytest -v
