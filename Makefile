.PHONY: up down

up:
	docker compose up --build --detach --wait

down:
	docker compose down
