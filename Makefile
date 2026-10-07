# SafeSol — Make targets from the Build Guide (make cache / make demo / make test).
# Windows without make: run the commands shown after each target by hand (see README).

PY ?= python
DEM ?= cache/raw/jezero_dem.tif
ORTHO ?= $(wildcard cache/raw/jezero_ortho.tif)
NAME ?= Jezero Crater
RES ?= 25
START ?= 2017-09-01
END ?= 2017-09-30
PORT ?= 8000

.PHONY: install synthetic ctx terrain storms cache fixtures test dev demo

install:
	$(PY) -m pip install -r requirements.txt

synthetic:            ## test terrain only, flagged as synthetic in the app
	$(PY) -m src.acquire.dem --synthetic

ctx:                  ## download real Jezero CTX DTM + orthoimage -> cache/raw/
	$(PY) -m src.acquire.ctx_dtm

terrain:              ## prepare cache/raw DEM -> cache/mars/
	$(PY) -m src.acquire.dem --dem $(DEM) --name "$(NAME)" --res $(RES) $(if $(ORTHO),--ortho $(ORTHO),)

storms:               ## real SEP events from NASA DONKI -> cache/storms.json
	$(PY) -m src.acquire.donki --start $(START) --end $(END)

cache: ctx terrain storms ## pre-fetch every demo input (run before the event)

fixtures:             ## copy the prepared cache into demo_fixtures/ so it is committed
	mkdir -p demo_fixtures/mars
	cp cache/mars/* demo_fixtures/mars/
	if [ -f cache/storms.json ]; then cp cache/storms.json demo_fixtures/storms.json; fi

test:
	$(PY) -m pytest

dev:
	$(PY) -m uvicorn src.api.main:app --reload --port $(PORT)

demo:                 ## the way it runs on stage: no network
	OFFLINE=1 $(PY) -m uvicorn src.api.main:app --port $(PORT)
