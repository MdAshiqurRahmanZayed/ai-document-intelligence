# AI disclosure

This project was built with AI assistance. This page says where, with what, and how the output was checked.

## Tools

- **Claude Code** (Anthropic's command-line coding assistant), using Claude models, for planning, code, tests, debugging and documentation. It worked in this repository with permission to read files, edit them and run commands; commits and pushes were made only when the author asked.
- **Google Gemini** is also part of the product itself (invoice extraction and embeddings at run time). That is a feature of the system, not a development aid; see [README](../README.md) and [security notes](security.md) for what is sent to it.

## What the AI helped with

| Area | Help given |
|---|---|
| Planning | Drafting OpenSpec change proposals, specs, designs and task lists for each phase (`openspec/`). |
| Backend | Upload, ingestion, OCR, extraction, validation, search, corrections and reprocess code, with their tests. |
| Frontend | The web interface (pages, components, the server-side proxy), with component and unit tests and one browser journey. |
| Infrastructure | Docker Compose services, the Flower dashboard, Makefile targets. |
| Debugging | Finding causes from logs and tests: missing migrations, a retired model ID, a duplicate-detection clash in sample data, a lint failure. |
| Documentation | This README, API and testing docs, security notes. |
| Sample data | A script that generates made-up invoices in every supported format. |

## How the output was checked

- **Automated:** unit, integration and component tests (`make test`), lint and type checks (`make lint`, `make check`), and a browser journey (`make e2e`). Tests never call the real model; they use fakes.
- **Against the specs:** each change had written requirements and scenarios; `openspec validate --strict` was run, and tasks were ticked only when their stated check passed.
- **Manual runs:** the stack was run in Docker and used through the browser with generated sample files. Several real defects were found this way and fixed (see the debugging row above).
- **Review:** the author read the changes, ran the commands, and decided what to merge. The AI did not push or merge on its own.
- **Facts in the docs** were taken from the code and configuration, not from memory (for example the service list, environment variables and routes).

## What remained the author's decisions

The task scope and the order of phases, the stack, which features to cut when time ran short (including the evaluation, which was not done; see [Known limits](../README.md#known-limits)), what to commit and push, and acceptance of each change.

## Limits of this disclosure

AI-assisted code can look right and be wrong. Extraction quality has not been measured on a labelled dataset, and security measures are described in [security.md](security.md) together with what they do not cover. Treat extracted values as proposals for a person to confirm.

*Draft for the author to review: edit any line that does not match how the work was actually done.*
