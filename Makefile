.PHONY: up down build logs shell migrate makemigrations ps prod-up prod-down

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f web

shell:
	docker compose exec web bash

migrate:
	docker compose exec web python manage.py migrate

makemigrations:
	docker compose exec web python manage.py makemigrations

ps:
	docker compose ps

prod-up:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

prod-down:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down
