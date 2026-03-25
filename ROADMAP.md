Codimension — Unified Roadmap

Phase 0 — Baseline stabilization

Ціль: стабільний запуск на Python 3.10+

Задачі

фіксація залежностей (pyproject)

усунення deprecated API

стабілізація Qt

базові сценарії (open file / build CFG)

Артефакти

reproducible env

CI (lint + run)

Acceptance

0 crash у базових сценаріях

deterministic behavior

Phase 1 — Test harness

Ціль: зафіксувати поведінку

Задачі

snapshot tests CFG

parser tests

regression suite

Артефакти

tests/core/*

Acceptance

будь-яка зміна CFG контрольована

Phase 2 — Boundary extraction

Ціль: відділити core від UI

Контракти

parse → AST build_cfg → Graph analyze → Metrics 

Задачі

винести parser / CFG / model

прибрати залежність від Qt

Acceptance

core працює без UI

Phase 3 — Modular monolith

Ціль: керована архітектура

Модулі

core.* app.* ui.* infra.* 

Acceptance

відсутні цикли

UI не впливає на core

=== КРИТИЧНИЙ БЛОК СЕРЕДОВИЩА ===

Phase 4 — Analysis Environment model

Ціль: достовірний аналіз

Сутність

AnalysisEnvironment 

Задачі

interpreter binding

env registry

project-level binding

Acceptance

кожен проект має активне env

Phase 5 — Environment introspection

Ціль: реальні дані середовища

Задачі

sys.path

site-packages

python version

platform

Acceptance

import resolution базується на реальних даних

Phase 6 — Analyzer binding

Ціль: всі аналізатори використовують env

Задачі

lint/type/test/run через env

dead code analysis через env

Acceptance

зміна env змінює результати аналізу

Phase 7 — Env cache + invalidation

Ціль: консистентність

Задачі

fingerprint env

reindex

cache invalidation

Acceptance

немає stale analysis

=== DEPENDENCIES + EXECUTION ===

Phase 8 — Dependency discovery

Ціль: автогенерація requirements

Задачі

import scan

package resolution

requirements synthesis

Артефакти

requirements.txt

pyproject draft

Acceptance

коректний dependency set

Phase 9 — Local venv backend

Ціль: ізольований запуск

Задачі

create/reuse env

install deps

binding до проекту

Acceptance

env створюється і працює з IDE

Phase 10 — Docker backend

Ціль: ізоляція runtime

Задачі

Dockerfile generation

build/run

artifact collection

Acceptance

аналіз виконується в контейнері

Phase 11 — Remote (SSH)

Ціль: робота з віддаленим кодом

Задачі

remote FS

remote exec

sync

Acceptance

проект відкривається по SSH і аналіз працює

Phase 12 — Unified Execution Target

Ціль: один контракт виконання

ExecutionTarget.run() 

Типи

venv

docker

ssh

k8s

Acceptance

плагіни не знають про backend

Phase 13 — Kubernetes backend (пізно)

Ціль: масштаб

Задачі

job orchestration

artifact retrieval

Acceptance

heavy analysis у cluster

=== CODE UNDERSTANDING CORE ===

Phase 14 — Symbol index + dependency graph

Ціль: база аналізу

Задачі

symbol table

references

import graph

call graph

Acceptance

fast navigation

global analysis

Phase 15 — Metric system

Ціль: уніфікація метрик

MetricProvider 

Метрики

LOC

complexity

nesting

Acceptance

метрики незалежні від UI

Phase 16 — Overlay system

Ціль: візуальна діагностика

Overlay

size

complexity

nesting

Acceptance

швидке перемикання

зрозуміла легенда

Phase 17 — Advanced metrics

Ціль: практична користь

Інтеграції

coverage

ruff

mypy/pyright

Acceptance

overlay відображає реальні проблеми

Phase 18 — Runtime profiling

Ціль: performance

Метрики

self time

total time

calls

Acceptance

heatmap по CFG

Phase 19 — Git analytics

Ціль: ризик

Метрики

churn

frequency

Acceptance

overlay нестабільних зон

Phase 20 — Composite risk

Ціль: інтегральна оцінка

risk = f(metrics) 

Acceptance

explainable risk score

=== ADVANCED GRAPH ===

Phase 21 — Graph engine redesign

Ціль: масштаб

Задачі

incremental CFG

caching

lazy render

Acceptance

великі файли без лагів

Phase 22 — Debugger graph mode

Ціль: runtime path

Acceptance

execution path visible

Phase 23 — Graph diff

Ціль: аналіз змін

Acceptance

CFG diff між ревізіями

Phase 24 — Data-flow / taint

Ціль: глибокий аналіз

Acceptance

source → sink tracking

=== PLUGINS ===

Phase 25 — Plugin system

Ціль: розширюваність

API

Plugin hooks 

Acceptance

сторонній plugin без змін core

=== AI ===

Phase 26 — AI layer

Ціль: підсилення

Фічі

graph-aware explanation

refactor hints

risk explanation

natural queries

Acceptance

AI працює через core API

не ламає deterministic analysis

=== OVERLAY EXTENSIONS (від env) ===

Phase 27 — Environment overlay

Ціль: показ контексту виконання

Показує

missing deps

inactive branches

platform constraints

Phase 28 — Dependency overlay

Ціль: структура залежностей

Phase 29 — Deployment overlay

Ціль: де виконується код

Фінальна архітектура

Code → AST → CFG → Symbol Index → Metrics → Overlay → UI Execution Targets (venv/docker/ssh/k8s) → Tooling (lint/test/profile) Plugins AI (через core) 

Ключові правила

Core не залежить від UI

Execution через один контракт

Environment — джерело істини

Overlay = окремий шар

AI тільки після детермінованого ядра

Підсумок

Цей план:

зберігає працездатність на кожному кроці

мінімізує регресії

будує систему від бази до складного

Кінцевий результат:

інструмент глибокого структурного аналізу Python-коду з реальним execution context