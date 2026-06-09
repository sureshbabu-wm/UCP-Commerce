# Copyright 2026 UCP Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""UCP Custom Agent Executor with Gemini and OpenAI Runners."""

import json
import logging
import os
import re
import inspect
from abc import ABC, abstractmethod
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentExtension, DataPart, Part, TextPart
from a2a.utils import (
    get_data_parts,
    new_agent_parts_message,
    new_agent_text_message,
)
from google import genai
from google.genai import types
from openai import AsyncOpenAI

from ucp_sdk.models.schemas.shopping.types.payment_instrument import (
    PaymentInstrument,
)
from ucp_sdk.models.schemas.ucp import ResponseCheckout as UcpMetadata

from .agent import ALL_TOOLS, SYSTEM_INSTRUCTION, ToolContext
from .constants import (
    A2A_UCP_EXTENSION_URL,
    ADK_EXTENSIONS_STATE_KEY,
    ADK_LATEST_TOOL_RESULT,
    ADK_PAYMENT_STATE,
    ADK_UCP_METADATA_STATE,
    ADK_USER_CHECKOUT_ID,
    UCP_AGENT_HEADER,
    UCP_CHECKOUT_KEY,
    UCP_PAYMENT_DATA_KEY,
    UCP_RISK_SIGNALS_KEY,
)
from .a2a_extensions import UcpExtension
from .ucp_profile_resolver import ProfileResolver


def function_to_openai_tool(func) -> dict:
    """Generate OpenAI JSON Schema definition for a Python function."""
    sig = inspect.signature(func)
    doc = func.__doc__ or ""
    # Extract description (everything before Args: or Returns:)
    description = doc.split("Args:")[0].strip()
    
    properties = {}
    required = []
    
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        param_type = "string"
        if param.annotation == int:
            param_type = "integer"
        elif param.annotation == float:
            param_type = "number"
        elif param.annotation == bool:
            param_type = "boolean"
        elif param.annotation == list or getattr(param.annotation, "__origin__", None) is list:
            param_type = "array"
            
        param_desc = ""
        for line in doc.split("\n"):
            line = line.strip()
            if line.startswith(f"{name}:"):
                param_desc = line.split(":", 1)[1].strip()
                break
        
        properties[name] = {
            "type": param_type,
            "description": param_desc or f"The {name} parameter."
        }
        
        if param.default == inspect.Parameter.empty:
            required.append(name)
            
    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    }


class ToolBinder:
    """Binds standard shopping tools to a specific tool context state."""

    def __init__(self, tool_context: ToolContext):
        self.tool_context = tool_context

    def search_shopping_catalog(self, query: str) -> dict:
        """Search the product catalog for products that match the given query.

        Args:
            query: Query for performing product search.
        """
        from .agent import search_shopping_catalog as real_func
        return real_func(self.tool_context, query)

    def add_to_checkout(self, product_id: str, quantity: int = 1) -> dict:
        """Add a product to the checkout session.

        Args:
            product_id: Product ID or SKU.
            quantity: Quantity.
        """
        from .agent import add_to_checkout as real_func
        return real_func(self.tool_context, product_id, quantity)

    def remove_from_checkout(self, product_id: str) -> dict:
        """Remove a product from the checkout session.

        Args:
            product_id: Product ID or SKU.
        """
        from .agent import remove_from_checkout as real_func
        return real_func(self.tool_context, product_id)

    def update_checkout(self, product_id: str, quantity: int) -> dict:
        """Update the quantity of a product in the checkout session.

        Args:
            product_id: Product ID or SKU.
            quantity: New quantity.
        """
        from .agent import update_checkout as real_func
        return real_func(self.tool_context, product_id, quantity)

    def get_checkout(self) -> dict:
        """Retrieve a Checkout Session."""
        from .agent import get_checkout as real_func
        return real_func(self.tool_context)

    def update_customer_details(
        self,
        first_name: str,
        last_name: str,
        street_address: str,
        address_locality: str,
        address_region: str,
        postal_code: str,
        address_country: str | None,
        extended_address: str | None = None,
        email: str | None = None,
    ) -> dict:
        """Add delivery address to the checkout.

        Args:
            first_name: First name of recipient.
            last_name: Last name of recipient.
            street_address: Street address.
            address_locality: Locality/City.
            address_region: Region/State.
            postal_code: Postal code.
            address_country: Country code.
            extended_address: Extended address.
            email: Email address.
        """
        from .agent import update_customer_details as real_func
        return real_func(
            self.tool_context,
            first_name,
            last_name,
            street_address,
            address_locality,
            address_region,
            postal_code,
            address_country,
            extended_address,
            email,
        )

    async def complete_checkout(self) -> dict:
        """Process the payment data to complete checkout."""
        from .agent import complete_checkout as real_func
        return await real_func(self.tool_context)

    def start_payment(self) -> dict:
        """Ask for required information to proceed with the payment."""
        from .agent import start_payment as real_func
        return real_func(self.tool_context)


class BaseRunner(ABC):
    """Abstract Base Runner for execution of LLM agents."""

    @abstractmethod
    async def run(self, query: str, state: dict, history: list) -> tuple[list[Part], list]:
        """Run message interaction loop and return result parts and updated history."""


class GeminiRunner(BaseRunner):
    """Runner using google-genai SDK for Gemini models."""

    def __init__(self):
        self.client = genai.Client()

    async def run(self, query: str, state: dict, history: list) -> tuple[list[Part], list]:
        tool_context = ToolContext(state)
        binder = ToolBinder(tool_context)
        
        tools = [
            binder.search_shopping_catalog,
            binder.add_to_checkout,
            binder.remove_from_checkout,
            binder.update_checkout,
            binder.get_checkout,
            binder.update_customer_details,
            binder.complete_checkout,
            binder.start_payment,
        ]

        chat = self.client.aio.chats.create(
            model="gemini-2.5-flash",
            history=history,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=tools,
            )
        )

        response = await chat.send_message(query)

        while response.function_calls:
            tool_responses = []
            for call in response.function_calls:
                method = getattr(binder, call.name, None)
                if not method:
                    result = {"status": "error", "message": f"Tool {call.name} not found"}
                else:
                    try:
                        if inspect.iscoroutinefunction(method):
                            result = await method(**call.args)
                        else:
                            result = method(**call.args)
                    except Exception as e:
                        logging.exception(f"Error running tool {call.name}")
                        result = {"status": "error", "message": str(e)}

                # Replaces after_tool_callback logic:
                extensions = state.get(ADK_EXTENSIONS_STATE_KEY, [])
                ucp_response_keys = [UCP_CHECKOUT_KEY, "a2a.product_results"]
                if UcpExtension.URI in extensions and any(
                    key in result for key in ucp_response_keys
                ):
                    state[ADK_LATEST_TOOL_RESULT] = result

                tool_responses.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=call.name,
                            response={"result": result}
                        )
                    )
                )

            response = await chat.send_message(tool_responses)

        updated_history = await chat.get_history()

        result_parts = []
        latest_result = state.get(ADK_LATEST_TOOL_RESULT)
        if latest_result:
            result_parts.append(Part(root=DataPart(data=latest_result)))
            state[ADK_LATEST_TOOL_RESULT] = None
        else:
            result_parts.append(Part(root=TextPart(text=response.text or "")))

        return result_parts, updated_history


class OpenAIRunner(BaseRunner):
    """Runner using openai SDK for GPT models."""

    def __init__(self):
        self.client = AsyncOpenAI()

    async def run(self, query: str, state: dict, history: list) -> tuple[list[Part], list]:
        tool_context = ToolContext(state)
        binder = ToolBinder(tool_context)
        
        openai_tools_list = [
            binder.search_shopping_catalog,
            binder.add_to_checkout,
            binder.remove_from_checkout,
            binder.update_checkout,
            binder.get_checkout,
            binder.update_customer_details,
            binder.complete_checkout,
            binder.start_payment,
        ]
        
        tools_schema = [function_to_openai_tool(t) for t in openai_tools_list]
        tool_map = {t.__name__: t for t in openai_tools_list}

        openai_history = list(history)
        if not openai_history:
            openai_history.append({"role": "system", "content": SYSTEM_INSTRUCTION})
            
        openai_history.append({"role": "user", "content": query})

        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=openai_history,
            tools=tools_schema,
        )

        message = response.choices[0].message
        openai_history.append(message)

        while message.tool_calls:
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                
                method = tool_map.get(func_name)
                if not method:
                    result = {"status": "error", "message": f"Tool {func_name} not found"}
                else:
                    try:
                        if inspect.iscoroutinefunction(method):
                            result = await method(**func_args)
                        else:
                            result = method(**func_args)
                    except Exception as e:
                        logging.exception(f"Error executing tool {func_name}")
                        result = {"status": "error", "message": str(e)}

                # Replaces after_tool_callback logic:
                extensions = state.get(ADK_EXTENSIONS_STATE_KEY, [])
                ucp_response_keys = [UCP_CHECKOUT_KEY, "a2a.product_results"]
                if UcpExtension.URI in extensions and any(
                    key in result for key in ucp_response_keys
                ):
                    state[ADK_LATEST_TOOL_RESULT] = result

                openai_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": json.dumps({"result": result})
                })

            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=openai_history,
                tools=tools_schema,
            )
            message = response.choices[0].message
            openai_history.append(message)

        result_parts = []
        latest_result = state.get(ADK_LATEST_TOOL_RESULT)
        if latest_result:
            result_parts.append(Part(root=DataPart(data=latest_result)))
            state[ADK_LATEST_TOOL_RESULT] = None
        else:
            result_parts.append(Part(root=TextPart(text=message.content or "")))

        return result_parts, openai_history


class UcpRequestProcessor:
    """Handle UCP-specific request processing."""

    def __init__(self, profile_resolver: ProfileResolver):
        self.profile_resolver = profile_resolver

    def prepare_ucp_metadata(self, context: RequestContext) -> UcpMetadata:
        if A2A_UCP_EXTENSION_URL not in context.requested_extensions:
            raise ValueError("UCP Extension is required for this agent")

        headers = context.call_context.state.get("headers")  # type: ignore

        ucp_agent_header_key = next(
            (key for key in headers if key.lower() == UCP_AGENT_HEADER.lower()),
            None,
        )

        if not ucp_agent_header_key:
            raise ValueError("UCP-Agent should be present in request headers")

        ucp_agent_header_value = headers[ucp_agent_header_key]

        match = re.search(r'profile="([^"]*)"', ucp_agent_header_value)
        if not match or not match.group(1):
            raise ValueError(
                "Client profile URL is missing or empty in UCP-Agent header"
            )

        client_profile_url = match.group(1)
        client_profile_metadata = self.profile_resolver.resolve_profile(
            client_profile_url
        )
        return self.profile_resolver.get_ucp_metadata(client_profile_metadata)


class CustomAgentExecutor(AgentExecutor):
    """Custom Agent Executor selecting Gemini or OpenAI dynamically."""

    def __init__(self, agent, extensions: list[AgentExtension]):
        # agent argument is kept for compatibility withDefaultRequestHandler signature
        self.extensions = extensions or []
        self.profile_resolver = ProfileResolver()
        self.ucp_processor = UcpRequestProcessor(self.profile_resolver)
        
        self.provider = os.getenv("AI_PROVIDER", "gemini").lower()
        if self.provider == "openai":
            self.runner = OpenAIRunner()
        else:
            self.runner = GeminiRunner()

        self.sessions = {}

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        raise NotImplementedError("Cancellation is not implemented.")

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        if not context.message:
            raise ValueError("Message should be present in request context")

        self._activate_extensions(context)
        ucp_metadata = self.ucp_processor.prepare_ucp_metadata(context)

        query, payment_data = self._prepare_input(context)
        session_id = context.context_id

        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "history": [],
                "state": {
                    ADK_UCP_METADATA_STATE: ucp_metadata,
                    ADK_EXTENSIONS_STATE_KEY: context.requested_extensions,
                    ADK_PAYMENT_STATE: payment_data,
                    ADK_LATEST_TOOL_RESULT: None,
                    ADK_USER_CHECKOUT_ID: None,
                }
            }

        session = self.sessions[session_id]
        state = session["state"]
        
        state[ADK_PAYMENT_STATE] = payment_data
        state[ADK_EXTENSIONS_STATE_KEY] = context.requested_extensions
        state[ADK_UCP_METADATA_STATE] = ucp_metadata

        try:
            result_parts, updated_history = await self.runner.run(
                query, state, session["history"]
            )
            session["history"] = updated_history
            await event_queue.enqueue_event(
                new_agent_parts_message(result_parts, context.context_id, None)
            )

        except Exception as e:
            logging.exception(f"Error in execution of runner for session {session_id}")
            await event_queue.enqueue_event(
                new_agent_text_message(
                    f"Error: {context.context_id} - {str(e)}",
                )
            )

    def _activate_extensions(self, context: RequestContext):
        if context.requested_extensions:
            for ext in self.extensions:
                if ext.uri in context.requested_extensions:
                    context.add_activated_extension(ext.uri)

    def _prepare_input(
        self,
        context: RequestContext,
    ) -> tuple[str, dict | None]:
        query = context.get_user_input()
        data_list = get_data_parts(context.message.parts)
        payment_payload: dict[str, Any] = {}
        payment_keys = [UCP_PAYMENT_DATA_KEY, UCP_RISK_SIGNALS_KEY]

        for data_part in data_list:
            for key in payment_keys:
                if key in data_part:
                    value = data_part.pop(key)
                    if key == UCP_PAYMENT_DATA_KEY:
                        payment_payload[key] = PaymentInstrument.model_validate(value)
                    else:
                        payment_payload[key] = value

            if data_part:
                query += "\n" + json.dumps(data_part)

        return query, payment_payload or None
