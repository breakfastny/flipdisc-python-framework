build:
	python setup.py sdist
	python setup.py bdist_wheel

clean:
	rm -rf build dist *.egg *.egg-info


.PHONY: build clean
