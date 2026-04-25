# Prompt Reliability Workflow

This repository documents a prompt testing project for repeated business tasks like summarization, extraction, and support drafting.

## Domain
Operations / GenAI

## Overview
Turned prompt writing into a repeatable evaluation process so teams could get more stable outputs instead of relying on one-off prompt experiments.

## Methodology
1. Grouped business tasks by pattern such as summarize, extract, classify, and reply so each task type could use the right prompt structure.
2. Created baseline prompts and structured variations using role instructions, few-shot examples, formatting rules, and task-specific wording.
3. Built a lightweight Python test harness to run repeated examples through Gemini Flash and collect outputs across multiple prompt versions.
4. Scored results against simple checks for format stability, completeness, and usefulness instead of trusting a single impressive run.
5. Tracked prompt versions, notes, and scores in Google Sheets so the team could understand why a prompt was selected and reused later.
6. Packaged the best-performing prompts into a reusable library and handbook that made prompt engineering feel operational rather than ad hoc.

## Skills
- Prompt Engineering
- Prompt Evaluation
- Gemini Flash
- Python Automation
- Google Sheets
- Few-Shot Design
- Output Format Control
- Prompt Library Design

## Source
This README was generated from the portfolio project data used by `/Users/harshitpanikar/Documents/Test_Projs/harshitpaunikar1.github.io/index.html`.
