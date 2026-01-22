# 🧠 MathMongoDB — Project Status and Pending Work

This document summarizes **what has already been achieved** in MathMongoDB and **what is still missing**, with a strong focus on the **Cuaderno (Experimental)** module and its evolution into a reproducible work‑and‑study operating system.

---

## ✅ Achievements (Current State)

### Core project

* [x] Main application built with **Streamlit**.
* [x] Persistence layer based on **MongoDB** using structured JSON documents.
* [x] Incremental architecture with **no massive refactors**.
* [x] Clear conceptual separation between:

  * Worklog (operational work record)
  * Backlog (task planning)
  * LaTeX Diary (deep reasoning and technical reflection)

---

### 📓 Cuaderno Module (Experimental)

The Cuaderno already works as an **operational hub** integrating multiple subsystems:

* [x] Summary dashboard (counts for Worklog, Backlog, Weekly, Deliverables, Diary).
* [x] Navigation via tabs:

  * Worklog
  * Backlog
  * Weekly Review
  * Deliverables
  * Kanban (placeholder)
  * Diary

---

### 🗂️ Worklog (Complete and Reference Module)

* [x] Create work entries (fast, plain text).
* [x] Edit existing entries.
* [x] Delete entries with explicit confirmation.
* [x] Create Worklog entries from Backlog items (one‑way integration).
* [x] List recent entries.
* [x] Query with filters:

  * Date range
  * Project
  * Status
  * Text contains
* [x] CSV export:

  * Manual selection from recent entries
  * Export from filtered queries

👉 **Worklog is the reference pattern** for UX and technical behavior.

---

### 📋 Backlog (Almost complete)

* [x] Create backlog items.
* [x] Edit status, priority, owner, and text.
* [x] List recent items.
* [x] CSV export from recent items.
* [x] CSV export using filters (aligned with Worklog).

---

### 📅 Weekly Review (Partially complete)

* [x] Capture by `ISO Year` + `ISO Week`.
* [x] Structured fields:

  * Weekly objectives
  * Wins
  * Blocks / risks
  * Plan for next week
* [x] Automatic aggregations:

  * Real hours from Worklog
  * Completed tasks from Backlog
* [x] Persistence in MongoDB (upsert per week).

---

## 🚧 Missing Features (What Still Needs to Be Done)

### 📅 Weekly Review — **Align with Worklog / Backlog**

Currently, Weekly Review only supports **capture and save**, but not full operational usage.

Missing features:

* [ ] List recent Weekly Reviews.
* [ ] Selector to **load and edit past weeks**.
* [ ] CSV export with the same modes as Worklog:

  * Select from recent weeks
  * Filtered query

    * `updated_at` range
    * ISO year
    * ISO week
    * Text contains (objectives, wins, blocks, plan)

Goal:

> Weekly Review must provide **exactly the same operational capabilities** as Worklog and Backlog.

---

### 📦 Deliverables — Current State and Pending Work

The Deliverables tab exists but is **functionally incomplete**.

Pending tasks:

* [ ] Define a clear Deliverable schema:

  * Title
  * Type (paper, code, report, class, etc.)
  * Project
  * Target date
  * Status
* [ ] Minimal CRUD:

  * Create
  * Edit
  * Delete
* [ ] List recent deliverables.
* [ ] Query with filters (identical to Worklog / Backlog).
* [ ] CSV export using the same standard modes.

---

### 📦 Non‑negotiable design principles

For **Weekly Review** and **Deliverables**:

* ❌ No complex editors.
* ❌ No mixing with the LaTeX Diary.
* ✅ Reuse existing patterns.
* ✅ UX identical to Worklog / Backlog.
* ✅ Minimal, controlled, and verifiable changes.

---

## 🔮 Future MVPs (Not yet a priority)

* [ ] Real Kanban connected to Backlog + Worklog.
* [ ] Explicit relationships between:

  * Backlog → Worklog → Deliverables → Weekly Review
* [ ] Export Weekly Review to Quarto / PDF.
* [ ] Monthly / quarterly review views.

---

## 🎯 Project Vision

MathMongoDB is **no longer just a mathematical concept database**.

It has evolved into:

> A personal system for **thinking, working, planning, and technical memory**,
> where each module has a clear and operational responsibility.

The next step is to **close the symmetry**:

> Worklog = Backlog = Weekly Review = Deliverables

Same capabilities. Different purposes.

---
