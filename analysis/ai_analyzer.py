import os
import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from openai import OpenAI
from spoon_ai.chat import ChatBot
from spoon_ai.agents import SpoonReactAI

from analysis.static_scanner import StaticFinding
from analysis.parser import ParsedContract

@dataclass
class AIFinding:
    severity: str
    title: str
    description: str
    location: str
    confidence: float
    reasoning: str
    suggested_fix: Optional[str] = None

class AIAnalyzer:
    """
    Orchestrates AI-powered vulnerability explanations.
    First uses OpenAI directly; then, if a SpoonOS API key is provided,
    it spins up a SpoonReactAI agent for additional analysis.
    """

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.spoon_key = os.getenv("SPOON_API_KEY")

        # Initialize OpenAI client (if key set)
        self.openai_client = OpenAI(api_key=self.openai_key) if self.openai_key else None

    def analyze(
        self,
        contract_path: str,
        parsed: ParsedContract,
        static_results: Dict[str, List[StaticFinding]]
    ) -> List[AIFinding]:
        findings: List[AIFinding] = []

        # Prepare a snippet of the source for context
        snippet = parsed.source_code[:1500]

        # 1. Direct OpenAI analysis
        if self.openai_client:
            try:
                prompt = self._build_prompt(parsed.name, snippet, static_results)
                resp = self.openai_client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are a Solidity security auditor."},
                        {"role": "user",   "content": prompt}
                    ],
                    max_tokens=1500,
                    temperature=0.1
                )
                content = resp.choices[0].message.content
                findings.extend(self._parse_openai_response(content))
            except Exception as e:
                if self.debug:
                    print(f"[ai] OpenAI error: {e}")

        # 2. SpoonOS Agent analysis via SDK
        if self.spoon_key:
            try:
                bot = SpoonReactAI(
                    llm=ChatBot(
                        llm_provider="openai",
                        model_name=os.getenv("SPOON_MODEL", "anthropic/claude-sonnet-4"),
                        api_key=self.spoon_key,
                        base_url=os.getenv("SPOON_BASE_URL", "https://api.openrouter.ai/api/v1")
                    ),
                    debug=self.debug
                )

                prompt = self._build_prompt(parsed.name, snippet, static_results)
                # run_sync returns the agent’s textual response
                response = bot.run_sync(prompt)
                # Expecting the agent to return JSON array of findings
                data = json.loads(response)
                findings.extend(self._parse_spoon_response(data.get("findings", [])))

            except Exception as e:
                if self.debug:
                    print(f"[ai] SpoonOS Agent error: {e}")

        return findings

    def _build_prompt(
        self,
        name: str,
        code_snippet: str,
        static_results: Dict[str, List[StaticFinding]]
    ) -> str:
        static_summary = "\n".join(
            f"- [{f.severity}] {f.title} at {f.location}"
            for bucket in static_results.values() for f in bucket
        ) or "No static findings."
        return (
            f"Analyze the Solidity contract `{name}` for security vulnerabilities.\n\n"
            f"Static Analysis Summary:\n{static_summary}\n\n"
            f"Source Code Snippet:\n```solidity\n{code_snippet}\n```\n\n"
            "Provide a JSON array of findings with fields:\n"
            "`severity`, `title`, `description`, `location`, `confidence`, `reasoning`, `suggested_fix`."
        )

    def _parse_openai_response(self, content: str) -> List[AIFinding]:
        findings: List[AIFinding] = []
        try:
            # Extract JSON array from the response
            start, end = content.find("["), content.rfind("]") + 1
            arr = json.loads(content[start:end])
            for item in arr:
                findings.append(AIFinding(**item))
        except Exception:
            if self.debug:
                print("[ai] Failed to parse OpenAI response")
        return findings

    def _parse_spoon_response(self, data: List[Dict[str, Any]]) -> List[AIFinding]:
        findings: List[AIFinding] = []
        for item in data:
            findings.append(AIFinding(
                severity=item.get("severity", "medium"),
                title=item.get("title", ""),
                description=item.get("description", ""),
                location=item.get("location", ""),
                confidence=item.get("confidence", 0.5),
                reasoning=item.get("reasoning", ""),
                suggested_fix=item.get("suggested_fix")
            ))
        return findings
