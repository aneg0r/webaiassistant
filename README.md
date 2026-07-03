# Web AI Assistant

Web AI Assistant is an open-source customer-facing agent widget designed for websites.

It enables visitors to interact with either AI agents or human operators through a simple chat interface. Unlike traditional live-chat tools, Web AI Assistant focuses on actionable workflows: agents can answer questions, guide users, collect information, and trigger business actions.

It aims to be between a traditional live chat widget and a complex enterprise agent platform: simple enough to deploy in minutes, powerful enough to automate real customer-facing tasks.

Visit http://webaiassistant.fr/ for realtime demo (in French).

## Why Web AI Assistant? Typical use cases

This agent can:

* Answer questions using your knowledge base (client service, customer support)
* Guide visitors through predefined processes (lead qualtification)
* Collect structured information (surveys, feedback)
* Execute simple business workflows (appointment requests, issue reporing)
* Escalate conversations to human operators when needed

Agent behavior is defined using simple Markdown task files (`__task__.md`), making it easy to configure and maintain without complex tooling.

## What Web AI Assistant Is Not

Web AI Assistant intentionally focuses on external interactions.

It is **not**:

* A CRM platform
* An internal employee assistant
* A secure enterprise agent platform
* An MCP-based orchestration framework
* A multi-channel messaging hub (not yet !)

The goal is to provide a lightweight, website-integrated agent that helps visitors accomplish tasks.

## Architecture

The project is intentionally simple to deploy and extend.

### Frontend

* Vanilla JavaScript widget
* Example HTML integration page
* Embeddable in a few lines of code
* Can easily be ported to React, Next.js, Vue, or other frontend frameworks

### Backend

* Lightweight Python backend
* Minimal dependencies
* REST endpoints managed through `agent.py`
* Can be ported to Node.js, Go, PHP, or other backend stacks
* LLM-agnostic (you can connect to Gemini, OpenAI, Mistral, ...)

### Storage

Choose the level of complexity you need:

* JSON / JSONL storage for simple deployments
* PostgreSQL for production environments

### Administration

A lightweight administration interface allows human operators to:

* Monitor conversations
* Reply to users
* Review pending actions
* Handle human-in-the-loop workflows

## Current Limitations

Not yet implemented:
* Channels integration (Slack, Discord, Telegram), but human operators are currently notified through custom integrations (dashboard and email)
* Complex workflows requiring a FSM, Finite-State-Machine. 

## Design Principles

* Simple deployment
* Minimal dependencies
* Human-in-the-loop 
* Easy customization
* Agent-first workflows
* Self-hosted and open source

## Getting started

See [INSTALLATION.md](INSTALLATION.md) for setup, configuration, API reference, and deployment details.
