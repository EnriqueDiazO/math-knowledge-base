# -----------------------------
# Paths (relative, no hardcode)
# -----------------------------
SHELL := /bin/bash
VENV := . mathdbmongo/bin/activate &&
PY := $(VENV) python
PY3 := $(VENV) python3
BOOK_TEMPLATE := quarto_book
BOOK_BUILD := quarto_book_build
EXPORTED_NOTES_DIR := exported_notes
EXPORTED_NOTES_BUILD_DIR := $(EXPORTED_NOTES_DIR)/_build

DATABASE ?= MathV0
STREAMLIT_HOST ?= 127.0.0.1
STREAMLIT_PORT ?= 8501
ADVANCED_READER_HOST ?= 127.0.0.1
ADVANCED_READER_PORT ?= 8766
LOG_LEVEL ?= info
ADVANCED_READER_URL_HOST := $(if $(filter ::1,$(ADVANCED_READER_HOST)),[$(ADVANCED_READER_HOST)],$(ADVANCED_READER_HOST))



.PHONY: start mongo stop restart status run run-streamlit advanced-reader gui lint export grafo \
        book-clean book-export book-preview book-render \
        clean clean-all book-clean-artifacts clean-book cuaderno-install cuaderno-status clean-notes

start:
	@$(MAKE) mongo

mongo:
	@sudo systemctl start mongod
	@sudo systemctl --no-pager status mongod || true

stop:
	@sudo systemctl stop mongod && echo "✅ MongoDB detenido."

restart:
	@sudo systemctl restart mongod && $(MAKE) status

status:
	@sudo systemctl status mongod

# -----------------------
# 🚀 Aplicación Principal
# -----------------------

run:
	mathdbmongo/bin/python -m mathmongo.local_runtime \
		--database "$(DATABASE)" \
		--streamlit-host "$(STREAMLIT_HOST)" \
		--streamlit-port "$(STREAMLIT_PORT)" \
		--advanced-reader-host "$(ADVANCED_READER_HOST)" \
		--advanced-reader-port "$(ADVANCED_READER_PORT)" \
		--log-level "$(LOG_LEVEL)"

run-streamlit:
	MONGODB_DB="$(DATABASE)" \
	MATHMONGO_ADVANCED_READER_URL="http://$(ADVANCED_READER_URL_HOST):$(ADVANCED_READER_PORT)" \
	mathdbmongo/bin/python -m streamlit run editor/editor_streamlit.py \
		--server.address "$(STREAMLIT_HOST)" \
		--server.port "$(STREAMLIT_PORT)"

advanced-reader:
	mathdbmongo/bin/python -m mathmongo.advanced_reader \
		--host "$(ADVANCED_READER_HOST)" \
		--port "$(ADVANCED_READER_PORT)" \
		--database "$(DATABASE)" \
		--log-level "$(LOG_LEVEL)"

gui:
	. mathdbmongo/bin/activate && python run_gui.py

# -----------------------
# 🧹 Lint y correcciones automáticas
# -----------------------

lint:
	ruff check . --fix

# -----------------------
# 📤 Exportar desde Mongo a Quarto
# -----------------------

export:
	$(PY) export/exportar_qmd_desde_mongo.py

# -----------------------
# 🔗 Grafo interactivo desde Mongo
# -----------------------

grafo:
	$(PY) grafo_interactivo/generador/generar_grafo.py

# -----------------------
# 📚 Documentación Quarto
# -----------------------

book-clean:
	rm -rf $(BOOK_BUILD)

book-export:
	$(PY3) scripts/export_quarto_book.py --template $(BOOK_TEMPLATE) --output $(BOOK_BUILD) --force

book-preview:
	cd $(BOOK_BUILD) && quarto preview

book-render:
	cd $(BOOK_BUILD) && quarto render --to pdf

export-book:
	$(PY3) scripts/export_quarto_book.py --output quarto_book_build --force

# -----------------------
# 🧼 Limpieza de archivos temporales
# -----------------------

clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -r {} +
	rm -rf .ruff_cache/


# Limpieza extendida
clean-all: clean
	rm -rf exportados/
	rm -rf build/ dist/ *.egg-info
	rm -rf .ipynb_checkpoints/
	rm -rf $(BOOK_BUILD)/


book-clean-artifacts:
	@test -d $(BOOK_BUILD) || (echo "No build dir: $(BOOK_BUILD)"; exit 0)
	rm -rf $(BOOK_BUILD)/_book
	find $(BOOK_BUILD) -name "*.html" -delete || true



clean-book: book-clean

book: book-clean book-export book-preview

book-html: book-clean book-export book-render



cuaderno-install:
	python scripts/install_cuaderno_mode.py

cuaderno-status:
	python scripts/install_cuaderno_mode.py --status

clean-notes:
	@echo "🧹 Cleaning exported notes (keeping directories)..."
	@if [ -d "$(EXPORTED_NOTES_DIR)" ]; then \
		find "$(EXPORTED_NOTES_DIR)" -mindepth 1 -maxdepth 1 ! -name "_build" -exec rm -rf {} + ; \
	fi
	@if [ -d "$(EXPORTED_NOTES_BUILD_DIR)" ]; then \
		rm -rf "$(EXPORTED_NOTES_BUILD_DIR)"/* ; \
	fi
	@echo "✅ exported_notes cleaned (directories preserved)"
