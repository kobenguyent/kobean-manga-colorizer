# 🎨 Kobean Manga Colorizer - Quick Commands (UV-Powered)

.PHONY: all run dev test lint format clean help

all: run

run:
	@./run.sh

dev:
	@./run.sh --reload

test:
	@uv run python -m unittest discover tests

lint:
	@uv run ruff check .

format:
	@uv run ruff format .

help:
	@./run.sh --help

