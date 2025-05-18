SHELL := /bin/bash
.PHONY: start mongo
# Inicia MongoDB
start:
	. mathdbmongo/bin/activate && make mongo

mongo:
	sudo systemctl start mongod
	sudo systemctl status mongod
# Detiene MongoDB
stop:
	. mathdbmongo/bin/activate && sudo systemctl stop mongod && echo "✅ MongoDB detenido."

# Reinicia MongoDB
restart:
	. mathdbmongo/bin/activate && sudo systemctl restart mongod && make status

# Muestra el estado de MongoDB
status:
	sudo systemctl status mongod

# Lanza la app de Streamlit (ajusta si tu archivo principal es otro)
run:
	. mathdbmongo/bin/activate && streamlit run app/main.py
