.PHONY: install init chat brief test
install:  ## pip install -e .[dev]
	pip install -e ".[dev]"
init:
	bizops init
chat:
	bizops chat
brief:
	bizops run "Give me a brief: last 7 days sales, low stock items, and open support tickets."
test:
	pytest
