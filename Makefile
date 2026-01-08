SHELL := /bin/bash
VENV := . mathdbmongo/bin/activate &&
PY := $(VENV) python
PY3 := $(VENV) python3
BOOK_TEMPLATE := quarto_book
BOOK_BUILD := quarto_book_build

.PHONY: start mongo stop restart status run gui lint export grafo \
        book-clean book-export book-preview book-render \
        clean clean-all book-clean-artifacts clean-book

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
	. mathdbmongo/bin/activate && streamlit run editor/editor_streamlit.py

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
	cd $(BOOK_BUILD) && quarto render

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
