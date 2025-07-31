SHELL := /bin/bash
.PHONY: start stop restart status run lint export grafo preview doc clean

# -----------------------
# 🔁 MongoDB Management
# -----------------------

start:
	. mathdbmongo/bin/activate && make mongo

mongo:
	sudo systemctl start mongod
	sudo systemctl status mongod

stop:
	. mathdbmongo/bin/activate && sudo systemctl stop mongod && echo "✅ MongoDB detenido."

restart:
	. mathdbmongo/bin/activate && sudo systemctl restart mongod && make status

status:
	sudo systemctl status mongod

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
	python export/exportar_qmd_desde_mongo.py

# -----------------------
# 🔗 Grafo interactivo desde Mongo
# -----------------------

grafo:
	python grafo_interactivo/generador/generar_grafo.py

# -----------------------
# 📚 Documentación Quarto
# -----------------------

preview:
	cd quarto_book && quarto preview

doc:
	cd quarto_book && quarto render

# -----------------------
# 🧼 Limpieza de archivos temporales
# -----------------------

clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -r {} +
	find quarto_book -type f -path "*/s/*.qmd" -delete


# Limpieza extendida
clean-all:
	find . -type d -name '__pycache__' -exec rm -r {} +;
	find . -type f -name '*.py[cod]' -delete
	find . -type f -name '*.log' -delete
	find . -type f -name '*.aux' -delete
	find . -type f -name '*.out' -delete
	find . -type f -name '*.toc' -delete
	find . -type f -name '*.pdf' -delete
	find . -type f -name '*.tex' -delete
	find . -type f -name '*.html' -delete
	rm -rf exportados/
	rm -rf .ruff_cache/
	rm -rf build/ dist/ *.egg-info
	rm -rf .ipynb_checkpoints/
	rm -rf quarto_book/*s/*.qmd



clean-book:
	rm -fv quarto_book/definicions/*.qmd
	rm -fv quarto_book/teoremas/*.qmd
	rm -fv quarto_book/ejemplos/*.qmd
	rm -fv quarto_book/proposicions/*.qmd
	rm -fv quarto_book/corolarios/*.qmd
	rm -fv quarto_book/lemas/*.qmd
	rm -fv quarto_book/otros/*.qmd
