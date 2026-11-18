# 🎨 Kobean Manga Colorizer - Quick Commands (UV-Powered)

.PHONY: all run dev test lint format clean help macos macos-build macos-test macos-icon

all: run

run:
	@./run.sh

dev:
	@./run.sh --reload

macos:
	@./kobean macos launch

macos-build:
	@./kobean macos build

macos-test:
	@./kobean macos test

macos-icon:
	@./kobean macos icon

test:
	@uv run python -m unittest discover tests

lint:
	@uv run ruff check .

format:
	@uv run ruff format .

help:
	@./run.sh --help

