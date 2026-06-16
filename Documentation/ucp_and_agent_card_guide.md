# Universal Commerce Protocol (UCP): Discovery Profile and Agent Card Guide

This guide provides a comprehensive explanation of how the Universal Commerce Protocol (UCP) handles discovery, capability configuration, and service routing. It details the relationship between REST discovery profiles and Agent-to-Agent (A2A) agent cards, clarifies key terminology (spec vs. schema), explores transport configurations, and explains the supporting files in the workspace.

---

## 1. Overview of UCP Discovery

The Universal Commerce Protocol defines two primary discovery mechanisms depending on the interaction architecture:

1. **REST / API-Based Discovery (`/.well-known/ucp` or [discovery_profile.json](file:///c:/Users/sureshbabum_500214/Projects/UCP%20Commerce/samples/rest/python/server/routes/discovery_profile.json)):**
   Used by standard web servers to declare what shopping capabilities they support and which protocols (transports) clients can use to communicate with them.
2. **Agent-to-Agent (A2A) Discovery ([agent_card.json](file:///c:/Users/sureshbabum_500214/Projects/UCP%20Commerce/samples/a2a/business_agent/src/business_agent/data/agent_card.json)):**
   Used by autonomous AI agents to broadcast their public identity, organizational details, conversational skills, and protocol extensions to other agents in a peer-to-peer or client-to-client environment.

---

## 2. Core Architectural Concepts

### Spec vs. Schema
A common point of confusion is the distinction between a **Spec (Specification)** and a **Schema**:

* **Specification (Spec):**
  * **What it is:** A human-readable description of how an API or feature behaves, its protocols, rules, and semantic expectations.
  * **Example URL:** `https://ucp.dev/2026-01-23/specification/shopping/checkout`
  * **Role:** It guides developers on *how* to implement the feature and what business logic to expect.
* **Schema:**
  * **What it is:** A machine-readable definition file (typically JSON Schema, OpenAPI, or OpenRPC) used for automated payload validation, type generation, and interface routing.
  * **Example URL:** `https://ucp.dev/2026-01-23/schemas/shopping/checkout.json`
  * **Role:** Frameworks use schemas at runtime to validate incoming JSON documents, reject malformed payloads, and map data parameters.

### Versions and Version Anchors
In UCP profiles, a `version` string (such as `2026-01-23`) is required at both the document root and individual service/transport configurations. 
* **The Root Version:** Sets the baseline protocol version for the entire discovery payload.
* **The Component Version:** Defines the exact version of the service or capability being offered. 

If these versions match, client and server can negotiate the handshake automatically. 

### The Mismatch Problem and Contract Breaches
When a server claims a particular version (e.g., `2026-01-23`) but references a schema corresponding to a different version (or structure), it causes a **contract breach**:
1. The client retrieves the discovery profile, notices the declared version, and formats its requests according to that version's schema.
2. The server receives the requests but validates them against its own internal data structures (often defined using Pydantic models).
3. If there is a schema mismatch, the framework rejects the request with a **`422 Unprocessable Entity`** validation error.

#### Standard vs. Custom Schemas
* **Standard Schemas:** Standardized capability structures defined by the UCP specification (e.g., checkout, fulfillment). Both client and server must adhere to them strictly.
* **Custom Schemas:** Extensible or merchant-specific capability schemas (e.g., `com.flower_shop.catalog`). Because both the client and server parse and validate against the specific JSON schema file referenced in the discovery profile, custom schemas do not cause contract breaches, provided the server's codebase aligns with the schema it publishes.

### Capability Inheritance and Extensions
UCP capabilities support inheritance using the `"extends"` field. For example, in [discovery_profile.json](file:///c:/Users/sureshbabum_500214/Projects/UCP%20Commerce/samples/rest/python/server/routes/discovery_profile.json):
```json
"dev.ucp.shopping.fulfillment": [
  {
    "version": "2026-01-23",
    "spec": "https://ucp.dev/2026-01-23/specification/fulfillment",
    "schema": "https://ucp.dev/2026-01-23/schemas/shopping/fulfillment.json",
    "extends": "dev.ucp.shopping.checkout"
  }
]
```
This means `fulfillment` is not a standalone process; it is a capability extension that builds upon the core `checkout` capability.

At the code level, this structure is implemented in Python through dynamic composition. Pydantic models like `UnifiedCheckoutUpdateRequest` use the `extra="allow"` configuration, permitting additional payload parameters (like fulfillment details or discount codes) to be added dynamically to the core checkout session object.

---

## 3. Comparison of Configuration Documents

| Feature | REST Discovery Profile (`discovery_profile.json`) | A2A Agent Card (`agent_card.json`) | A2A Config (`ucp.json`) |
| :--- | :--- | :--- | :--- |
| **Primary File** | [discovery_profile.json](file:///c:/Users/sureshbabum_500214/Projects/UCP%20Commerce/samples/rest/python/server/routes/discovery_profile.json) | [agent_card.json](file:///c:/Users/sureshbabum_500214/Projects/UCP%20Commerce/samples/a2a/business_agent/src/business_agent/data/agent_card.json) | [ucp.json](file:///c:/Users/sureshbabum_500214/Projects/UCP%20Commerce/samples/a2a/business_agent/src/business_agent/data/ucp.json) |
| **Audience** | External clients querying the REST server. | External agents connecting to the A2A agent. | Internal business agent backend server. |
| **Structure Style** | **Modern Array-Based:** Services and capabilities are structured as lists of objects (supporting multiple versions/transports). | **Agent Manifest Format:** Structured with metadata, capabilities, extensions, and natural language skills. | **Legacy Nested-Keys:** Services are structured as nested JSON objects mapping namespace names directly to version/spec objects. |
| **Endpoint Location** | Exposed at the standard `/.well-known/ucp` route. | Exposed at `/.well-known/agent-card.json`. | Not exposed publicly. Internal configuration file. |

### Why `ucp.json` and `agent_card.json` Coexist in A2A
In the Agent-to-Agent setup, both files are critical but serve different scopes:
* **[agent_card.json](file:///c:/Users/sureshbabum_500214/Projects/UCP%20Commerce/samples/a2a/business_agent/src/business_agent/data/agent_card.json):** This is the **public-facing manifest** (identity card) of the agent. When other agents connect, they fetch this file to see what capabilities the agent has, its preferred transport (`JSONRPC`), and its natural-language "skills" (which allow an LLM or router to matching queries like *"Help me find a shirt"* to the `product_search` skill).
* **[ucp.json](file:///c:/Users/sureshbabum_500214/Projects/UCP%20Commerce/samples/a2a/business_agent/src/business_agent/data/ucp.json):** This is the **internal configuration** of the business agent. The agent uses it during initialization to define which local parameters to load (such as the specific payment handlers, payment client configurations, and active specifications).

### Array-Based vs. Legacy Nested Structure
A key design difference exists between A2A and REST configurations:
* **REST/Modern Array-Based:**
  ```json
  "dev.ucp.shopping": [
    {
      "version": "2026-01-23",
      "transport": "rest",
      "endpoint": "{{ENDPOINT}}",
      "schema": "https://ucp.dev/2026-01-23/services/shopping/openapi.json"
    }
  ]
  ```
  Using an array allows the server to expose multiple variants of the same service (e.g., exposing a REST transport with an OpenAPI schema AND an MCP transport with an OpenRPC schema side-by-side).
* **A2A/Legacy Nested-Keys:**
  ```json
  "services": {
    "dev.ucp.shopping": {
      "version": "2026-01-23",
      "spec": "https://ucp.dev/2026-01-23/specification/shopping",
      "a2a": {
        "endpoint": "http://localhost:10999/.well-known/agent-card.json"
      }
    }
  }
  ```
  This is a legacy, single-value mapping format designed for straightforward internal routing where only one transport type (`a2a`) is active for the local shopping service.

---

## 4. Transport Types Breakdown

UCP profiles define how clients can interact with a shopping service using four distinct transport types:

1. **REST:**
   * **Endpoint:** Required (e.g., `http://localhost:8000/`)
   * **Schema:** Required (typically an OpenAPI schema path like `openapi.json`)
   * **Mechanism:** Traditional HTTP methods (`POST`, `PUT`, `GET`) to update and query resource states.
2. **MCP (Model Context Protocol):**
   * **Endpoint:** Required (e.g., `http://localhost:8000/mcp`)
   * **Schema:** Required (typically an OpenRPC schema path like `openrpc.json`)
   * **Mechanism:** A JSON-RPC protocol designed to expose contextual data and tools directly to LLMs/AI models.
3. **A2A (Agent-to-Agent):**
   * **Endpoint:** Required (e.g., `http://localhost:10999/.well-known/agent-card.json`)
   * **Schema:** Not directly referenced at the transport level.
   * **Mechanism:** Communication happens via a standard JSON-RPC envelope over WebSocket or HTTP, with capabilities defined inside the agent card.
4. **Embedded:**
   * **Endpoint:** **None** (omitted or null)
   * **Schema:** Required (specifies the API structure mapping)
   * **Mechanism:** Executed in-process. The consumer imports the service code directly into their application and calls functions in-memory.

---

## 5. The USB Keyboard Analogy

To understand why UCP requires granular capability lists rather than a single URL reference, consider the analogy of a **USB Keyboard**:

```
+--------------------------------------------------------------------------------+
|                             USB KEYBOARD ANALOGY                               |
+--------------------------------------------------------------------------------+
|                                                                                |
|  1. USB Device Connection:                                                     |
|     When you plug in a USB keyboard, it announces its Device Class (Class 03 -  |
|     Human Interface Device / HID).                                             |
|                                                                                |
|  2. Standard Host Assumptions:                                                 |
|     Because it is a standard HID Class, the operating system (Host) immediately |
|     knows how to communicate with it. It knows the device sends keycodes, and  |
|     requires no custom driver installation to type standard letters.           |
|                                                                                |
|  3. Custom Extension Handling:                                                 |
|     However, if the keyboard has custom features (e.g., an integrated OLED     |
|     screen or programmable macro keys), the standard HID driver is not enough. |
|     The keyboard must announce these custom capabilities so the OS can load    |
|     appropriate companion software.                                            |
|                                                                                |
|  4. How UCP Compares:                                                          |
|     * The Service (dev.ucp.shopping) is like the USB HID Device Class.         |
|     * The Capabilities (checkout, fulfillment, discount) are like standard/    |
|       custom features.                                                         |
|     * Since not all commerce sites support every option (e.g., digital-only    |
|       stores do not support fulfillment, while offline stores do not support   |
|       payment capture via webhooks), a merchant cannot just say "I do REST".   |
|       They must explicitly announce their capabilities so client agents can    |
|       dynamically adapt the UI, checkout forms, and user flow.                 |
|                                                                                |
+--------------------------------------------------------------------------------+
```

Embedding these capabilities inside the `agent_card.json` or discovery profile avoids round-trip network requests (lowering latency) and supports offline, peer-to-peer handshakes in decentralized A2A environments.

---

## 6. UCP REST Endpoints and Resource Lifecycle

UCP uses a simplified, unified resource lifecycle centered around the **Checkout Session**:

```mermaid
graph TD
    A[Start Checkout] --> B[Create Checkout Session]
    B --> C{Update Details}
    C -->|Add Address| D[PUT /checkout-sessions/{id}]
    C -->|Apply Coupon| D
    C -->|Choose Shipping| D
    D --> E[Status: ready_for_complete]
    E --> F[Complete Checkout: POST /checkout-sessions/{id}/complete]
    F --> G[Retrieve Order: GET /orders/{id}]
```

### The Single Resource Update Model
Unlike traditional e-commerce frameworks that have separate endpoints for `POST /shipping-address`, `POST /coupons`, or `POST /shipping-method`, UCP relies on a single **Checkout Session** resource.
* To perform any updates, the client issues a `PUT /checkout-sessions/{id}` request containing the entire updated checkout document.
* The backend (e.g., [checkout_service.py](file:///c:/Users/sureshbabum_500214/Projects/UCP%20Commerce/samples/rest/python/server/services/checkout_service.py)) recalculates totals, shipping options, and taxes in a single step, ensuring the state remains highly consistent.

### Order Retrieval
Once a checkout session is successfully completed, the checkout session object is cleaned up, and a formal order record is created. Clients retrieve this completed order using a standard **`GET /orders/{id}`** call, implemented in [order.py](file:///c:/Users/sureshbabum_500214/Projects/UCP%20Commerce/samples/rest/python/server/routes/order.py).

---

## 7. Payment Handlers and Signing Keys

UCP delegates actual payment instrument processing (like credit cards or mobile wallets) to specialized components called **Payment Handlers** (e.g., Google Pay or Shop Pay).

* **Registration:** Active handlers are declared under the `payment_handlers` section of the discovery profile and mapped internally in [ucp.json](file:///c:/Users/sureshbabum_500214/Projects/UCP%20Commerce/samples/a2a/business_agent/src/business_agent/data/ucp.json).
* **Webhook Communication:** When a third-party handler captures a payment, it communicates the status back to the UCP merchant backend via webhooks.
* **Signing Keys:** To guarantee that webhook payloads are legitimate and have not been tampered with or replayed:
  * The payment handler signs the payload with a **private key**.
  * The UCP merchant server validates the signature using the corresponding **public key** (registered in the signing key configuration), establishing a secure trust boundary.

---

## 8. Catalog Data and Mock Database (`products.json`)

To support testing, searches, and validations without requiring a live database connection, the samples include a mock catalog database in [products.json](file:///c:/Users/sureshbabum_500214/Projects/UCP%20Commerce/samples/a2a/business_agent/src/business_agent/data/products.json).

* **Initialization:** During startup, the store manager ([store.py](file:///c:/Users/sureshbabum_500214/Projects/UCP%20Commerce/samples/a2a/business_agent/src/business_agent/store.py)) reads `products.json` and parses the items into a structured dictionary of Pydantic `Product` models in-memory.
* **Usage:** 
  * Exposes search capabilities via the `search_products` method.
  * Validates SKU existence and retrieves prices (`offers.price`) when items are added to a checkout session via `add_to_checkout`.

---

## 9. Debugging and Troubleshooting Discovery

If you suspect the discovery mapping or version handshake is failing:

1. **Set Breakpoints:** Place a standard Python breakpoint in the discovery route handler [discovery.py](file:///c:/Users/sureshbabum_500214/Projects/UCP%20Commerce/samples/rest/python/server/routes/discovery.py):
   ```python
   breakpoint()
   ```
2. **Inspect Variables:** When the code pauses, use the Python debugger (Pdb) command line to examine the loaded configuration profile:
   ```text
   (Pdb) p profile
   (Pdb) p profile["ucp"]["services"]
   ```
3. **Validate Interface:** Start the server and visit the interactive Swagger UI (`/docs`) to test the discovery endpoints manually.
