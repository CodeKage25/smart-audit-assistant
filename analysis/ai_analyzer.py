"""
Pipeline Manager - Advanced AI Pipeline Architecture for Smart Contract Analysis
Enhanced with SpoonOS Agent Integration
"""

import os
import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import logging

# Try to import advanced ML libraries
try:
    import numpy as np
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.cluster import KMeans
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# Handle different OpenAI library versions
try:
    from openai import OpenAI
    OPENAI_V1 = True
except ImportError:
    try:
        import openai
        OPENAI_V1 = False
    except ImportError:
        openai = None
        OPENAI_V1 = False

# Try to import SpoonOS components
SPOON_AVAILABLE = False
try:
    # Preferred: package often exposes underscore name for hyphenated PyPI package
    from spoon_ai.chat import ChatBot
    from spoon_ai.agents import SpoonReactAI, SpoonReactMCP, ToolCallAgent
    from spoon_ai.tools.base import BaseTool
    from spoon_ai.tools import ToolManager
    SPOON_AVAILABLE = True
except ImportError:
        ChatBot = None
        ToolCallAgent = object
        ToolManager = None
        BaseTool = object

from analysis.parser import SolidityParser, ParsedContract
from analysis.static_scanner import StaticScanner, StaticFinding

@dataclass
class AIFinding:
    severity: str
    title: str
    description: str
    location: str
    confidence: float
    reasoning: str
    suggested_fix: Optional[str] = None

@dataclass
class PipelineConfig:
    """Configuration for analysis pipeline"""
    name: str
    description: str
    stages: List[str]
    parallel_stages: bool = True
    cache_enabled: bool = True
    timeout_seconds: int = 300
    max_workers: int = 4
    ai_models: List[str] = None
    static_tools: List[str] = None
    spoon_agent_type: str = "react"  # react, spoon_react_mcp
    
    def __post_init__(self):
        if self.ai_models is None:
            self.ai_models = ["gpt-4", "claude-3-sonnet"]
        if self.static_tools is None:
            self.static_tools = ["slither", "mythril", "solhint"]

# SpoonOS Security Analysis Tool
class SpoonSecurityTool(BaseTool):
    """Custom tool for security analysis within SpoonOS agents"""
    
    name: str = "security_analysis"
    description: str = "Analyze smart contracts for security vulnerabilities"
    parameters: dict = {
        "type": "object",
        "properties": {
            "contract_code": {
                "type": "string",
                "description": "The smart contract source code to analyze"
            },
            "contract_name": {
                "type": "string",
                "description": "Name of the contract being analyzed"
            },
            "static_findings": {
                "type": "string",
                "description": "Static analysis results as context"
            },
            "analysis_depth": {
                "type": "string",
                "enum": ["basic", "thorough", "comprehensive"],
                "description": "Depth of analysis to perform"
            }
        },
        "required": ["contract_code", "contract_name"]
    }

    async def execute(
        self, 
        contract_code: str, 
        contract_name: str, 
        static_findings: str = "", 
        analysis_depth: str = "thorough"
    ) -> str:
        """Execute security analysis"""
        
        # Define analysis prompts based on depth
        analysis_prompts = {
            "basic": "Identify critical security vulnerabilities only",
            "thorough": "Perform comprehensive security analysis including gas optimization",
            "comprehensive": "Deep security analysis with attack vectors and complex scenarios"
        }
        
        prompt = f"""
        Analyze this Solidity contract for security vulnerabilities:

        CONTRACT: {contract_name}
        ANALYSIS DEPTH: {analysis_depth.upper()}
        FOCUS: {analysis_prompts.get(analysis_depth, "Standard analysis")}

        STATIC ANALYSIS CONTEXT:
        {static_findings if static_findings else "No static analysis available"}

        SOURCE CODE:
        ```solidity
        {contract_code[:2500]}  # Limit to prevent token overflow
        ```

        Identify:
        1. Security vulnerabilities (reentrancy, access control, overflow)
        2. Gas optimization opportunities
        3. Logic errors and edge cases
        4. Best practice violations

        Return findings as JSON array with severity, title, description, location, confidence, reasoning, and suggested_fix.
        """
        
        return prompt  # Return the analysis prompt - the agent will process this

class SpoonContractAgent(ToolCallAgent):
    """Custom SpoonOS agent specialized for smart contract analysis"""
    
    name: str = "contract_analyzer"
    description: str = "AI agent specialized in smart contract security analysis"
    
    system_prompt: str = """You are an expert Solidity security auditor and smart contract analyst.
    You have deep knowledge of:
    - Smart contract vulnerabilities and attack vectors
    - Gas optimization techniques
    - Solidity best practices and design patterns
    - DeFi protocols and common pitfalls
    - MEV and front-running protection

    When analyzing contracts, provide detailed, actionable findings with:
    - Clear severity levels (critical, high, medium, low, info)
    - Specific locations and line references
    - Technical explanations of vulnerabilities
    - Concrete remediation steps
    - Confidence scores for each finding

    Always respond with valid JSON arrays containing finding objects."""

    next_step_prompt: str = "What security analysis should I perform next?"
    max_steps: int = 8

    def __init__(self, llm=None, **kwargs):
        # Set up available tools
        from pydantic import Field
        
        available_tools = ToolManager([
            SpoonSecurityTool(),
        ])
        
        super().__init__(available_tools=available_tools, llm=llm, **kwargs)

class AIAnalyzer:
    """
    Enhanced AI analyzer supporting both direct OpenAI and SpoonOS agents.
    """

    def __init__(self, debug: bool = False, use_spoon_agent: bool = False, spoon_agent_type: str = "react"):
        self.debug = debug
        self.use_spoon_agent = use_spoon_agent
        self.spoon_agent_type = spoon_agent_type
        
        # OpenAI configuration
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("BASE_URL", "https://api.openai.com/v1")
        self.model_name = os.getenv("MODEL_NAME", "gpt-4")
        
        # SpoonOS configuration
        self.spoon_key = os.getenv("SPOON_API_KEY") or self.openai_key
        self.spoon_model = os.getenv("SPOON_MODEL", "anthropic/claude-3-5-sonnet-20241022")
        self.spoon_base_url = os.getenv("SPOON_BASE_URL", "https://openrouter.ai/api/v1")
        
        # Initialize OpenAI client
        self.openai_client = None
        if self.openai_key and not use_spoon_agent:
            if OPENAI_V1:
                self.openai_client = OpenAI(
                    api_key=self.openai_key,
                    base_url=self.base_url
                )
            elif openai:
                openai.api_key = self.openai_key
                if self.base_url != "https://api.openai.com/v1":
                    openai.api_base = self.base_url
                self.openai_client = openai

        # Initialize SpoonOS agent
        self.spoon_agent = None
        if use_spoon_agent and SPOON_AVAILABLE and self.spoon_key:
            try:
                llm = ChatBot(
                    llm_provider="openai",  # Provider for SpoonOS
                    model_name=self.spoon_model,
                    api_key=self.spoon_key,
                    base_url=self.spoon_base_url
                )
                
                if spoon_agent_type == "spoon_react_mcp":
                    self.spoon_agent = SpoonReactMCP(llm=llm, debug=debug)
                elif spoon_agent_type == "custom":
                    self.spoon_agent = SpoonContractAgent(llm=llm, debug=debug)
                else:  # Default to react
                    self.spoon_agent = SpoonReactAI(llm=llm, debug=debug)
                    
            except Exception as e:
                if debug:
                    print(f"[ai] Failed to initialize SpoonOS agent: {e}")
                self.spoon_agent = None
        
        if debug:
            print(f"[ai] OpenAI available: {bool(self.openai_client)}")
            print(f"[ai] SpoonOS available: {SPOON_AVAILABLE}")
            print(f"[ai] SpoonOS agent initialized: {bool(self.spoon_agent)}")
            print(f"[ai] Using SpoonOS: {use_spoon_agent}")
            print(f"[ai] SpoonOS agent type: {spoon_agent_type}")

    def analyze(
        self,
        contract_path: str,
        parsed: ParsedContract,
        static_results: Dict[str, List[StaticFinding]]
    ) -> List[AIFinding]:
        findings: List[AIFinding] = []

        # Prepare contract snippet and static context
        snippet = parsed.source_code[:2500]
        static_summary = "\n".join(
            f"- [{f.severity.upper()}] {f.title} at {f.location}: {f.tool}"
            for bucket in static_results.values() for f in bucket
        ) or "No static findings detected."

        # Use SpoonOS agent if configured
        if self.use_spoon_agent and self.spoon_agent:
            try:
                spoon_findings = self._analyze_with_spoon_agent(
                    parsed.name, snippet, static_summary
                )
                findings.extend(spoon_findings)
                if self.debug:
                    print(f"[ai] SpoonOS agent found {len(spoon_findings)} issues")
            except Exception as e:
                if self.debug:
                    print(f"[ai] SpoonOS agent error: {e}")
                    import traceback
                    traceback.print_exc()

        # Fallback to direct OpenAI if SpoonOS fails or not configured
        if not findings and self.openai_client:
            try:
                prompt = self._build_prompt(parsed.name, snippet, static_results)
                
                if OPENAI_V1:
                    resp = self.openai_client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": "You are an expert Solidity security auditor. Analyze smart contracts for vulnerabilities and provide detailed findings in JSON format."},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=2000,
                        temperature=0.1
                    )
                    content = resp.choices[0].message.content
                else:
                    resp = self.openai_client.ChatCompletion.create(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": "You are an expert Solidity security auditor. Analyze smart contracts for vulnerabilities and provide detailed findings in JSON format."},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=2000,
                        temperature=0.1
                    )
                    content = resp.choices[0].message.content
                
                ai_findings = self._parse_openai_response(content)
                findings.extend(ai_findings)
                if self.debug:
                    print(f"[ai] OpenAI found {len(ai_findings)} issues")
                    
            except Exception as e:
                if self.debug:
                    print(f"[ai] OpenAI error: {e}")

        return findings

    def _analyze_with_spoon_agent(self, contract_name: str, code_snippet: str, static_summary: str) -> List[AIFinding]:
        """Analyze using SpoonOS agent"""
        if not self.spoon_agent:
            return []
        
        try:
            # Clear agent state
            self.spoon_agent.clear()
            
            # Build analysis prompt
            if hasattr(self.spoon_agent, 'avaliable_tools') and any(tool.name == "security_analysis" for tool in self.spoon_agent.avaliable_tools.tools):
                # Use custom tool for SpoonContractAgent
                prompt = f"""Analyze the smart contract '{contract_name}' for security vulnerabilities.

                Use the security_analysis tool with the following parameters:
                - contract_code: The provided source code
                - contract_name: {contract_name}
                - static_findings: {static_summary}
                - analysis_depth: thorough

                Source code:
                {code_snippet}

                Focus on critical security issues and provide detailed findings."""
            else:
                # Direct analysis for standard agents
                prompt = f"""Analyze this Solidity contract '{contract_name}' for security vulnerabilities:

                STATIC ANALYSIS RESULTS:
                {static_summary}

                CONTRACT SOURCE CODE:
                ```solidity
                {code_snippet}
                ```

                Analyze for:
                1. Reentrancy vulnerabilities
                2. Access control issues
                3. Integer overflow/underflow
                4. Unchecked external calls
                5. Gas optimization issues
                6. Logic errors

                Respond with a JSON array of findings. Each finding should have:
                - severity: "critical", "high", "medium", "low", or "info"
                - title: Brief descriptive title
                - description: Detailed explanation
                - location: File location or function name
                - confidence: Float between 0.0-1.0
                - reasoning: Why this is a vulnerability
                - suggested_fix: How to fix it

                Return ONLY the JSON array."""

            # Run agent analysis
            if hasattr(self.spoon_agent, 'run_sync'):
                response = self.spoon_agent.run_sync(prompt)
            else:
                import asyncio
                response = asyncio.run(self.spoon_agent.run(prompt))
            
            # Parse response
            findings = self._parse_agent_response(response)
            return findings
            
        except Exception as e:
            if self.debug:
                print(f"[ai] SpoonOS agent analysis failed: {e}")
                import traceback
                traceback.print_exc()
            return []

    def _parse_agent_response(self, response: str) -> List[AIFinding]:
        """Parse response from SpoonOS agent"""
        findings = []
        
        try:
            # Try to extract JSON from response
            response = response.strip()
            
            # Look for JSON array in response
            start = response.find("[")
            end = response.rfind("]") + 1
            
            if start != -1 and end > start:
                json_str = response[start:end]
                data = json.loads(json_str)
                
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            findings.append(AIFinding(
                                severity=item.get("severity", "medium").lower(),
                                title=item.get("title", "Security Issue"),
                                description=item.get("description", ""),
                                location=item.get("location", "Unknown"),
                                confidence=float(item.get("confidence", 0.5)),
                                reasoning=item.get("reasoning", ""),
                                suggested_fix=item.get("suggested_fix")
                            ))
            else:
                # Fallback: extract structured information from text
                findings = self._extract_findings_from_text(response)
                
        except (json.JSONDecodeError, ValueError) as e:
            if self.debug:
                print(f"[ai] Failed to parse agent response as JSON: {e}")
                print(f"[ai] Response: {response[:500]}...")
            
            # Fallback to text parsing
            findings = self._extract_findings_from_text(response)
        
        return findings

    def _extract_findings_from_text(self, text: str) -> List[AIFinding]:
        """Extract findings from natural language response"""
        findings = []
        lines = text.split('\n')
        current_finding = {}
        
        for line in lines:
            line = line.strip()
            if any(line.startswith(prefix) for prefix in ['Severity:', '**Severity:', 'SEVERITY:']):
                current_finding['severity'] = line.split(':', 1)[1].strip().lower()
            elif any(line.startswith(prefix) for prefix in ['Title:', '**Title:', 'TITLE:']):
                current_finding['title'] = line.split(':', 1)[1].strip()
            elif any(line.startswith(prefix) for prefix in ['Description:', '**Description:', 'DESCRIPTION:']):
                current_finding['description'] = line.split(':', 1)[1].strip()
            elif any(line.startswith(prefix) for prefix in ['Location:', '**Location:', 'LOCATION:']):
                current_finding['location'] = line.split(':', 1)[1].strip()
            elif line.startswith('---') and current_finding:
                # End of finding
                findings.append(AIFinding(
                    severity=current_finding.get('severity', 'medium'),
                    title=current_finding.get('title', 'Security Issue'),
                    description=current_finding.get('description', ''),
                    location=current_finding.get('location', ''),
                    confidence=0.7,
                    reasoning="Extracted from SpoonOS agent response"
                ))
                current_finding = {}
        
        # Handle last finding if no closing ---
        if current_finding:
            findings.append(AIFinding(
                severity=current_finding.get('severity', 'medium'),
                title=current_finding.get('title', 'Security Issue'),
                description=current_finding.get('description', ''),
                location=current_finding.get('location', ''),
                confidence=0.7,
                reasoning="Extracted from SpoonOS agent response"
            ))
        
        return findings

    def _build_prompt(
        self,
        name: str,
        code_snippet: str,
        static_results: Dict[str, List[StaticFinding]]
    ) -> str:
        static_summary = "\n".join(
            f"- [{f.severity.upper()}] {f.title} at {f.location}: {f.tool}"
            for bucket in static_results.values() for f in bucket
        ) or "No static findings detected."
        
        return f"""Analyze this Solidity contract '{name}' for security vulnerabilities and provide a comprehensive security assessment.

STATIC ANALYSIS RESULTS:
{static_summary}

CONTRACT SOURCE CODE:
```solidity
{code_snippet}
```

Please analyze the code for:
1. Reentrancy vulnerabilities
2. Access control issues  
3. Integer overflow/underflow
4. Unchecked external calls
5. Gas optimization issues
6. Logic errors
7. Front-running vulnerabilities
8. Any other security concerns

Respond with a JSON array containing detailed findings. Each finding should have:
- severity: "critical", "high", "medium", "low", or "info"
- title: Brief descriptive title
- description: Detailed explanation of the vulnerability
- location: File location (use contract name if line unknown)
- confidence: Float between 0.0-1.0 indicating certainty
- reasoning: Why this is a vulnerability
- suggested_fix: How to fix it (optional)

Example format:
[
  {{
    "severity": "high",
    "title": "Reentrancy vulnerability in withdraw function",
    "description": "The withdraw function makes external calls before updating state, allowing for reentrancy attacks",
    "location": "{name}:25-30",
    "confidence": 0.9,
    "reasoning": "External call to user.call{{value: amount}}() occurs before balance update",
    "suggested_fix": "Use checks-effects-interactions pattern: update state before external calls"
  }}
]

IMPORTANT: Return ONLY the JSON array, no additional text."""

    def _parse_openai_response(self, content: str) -> List[AIFinding]:
        findings: List[AIFinding] = []
        if not content:
            if self.debug:
                print("[ai] Empty response from OpenAI")
            return findings
            
        try:
            # Clean the response - remove markdown formatting if present
            cleaned_content = content.strip()
            if cleaned_content.startswith('```json'):
                cleaned_content = cleaned_content[7:]
            if cleaned_content.endswith('```'):
                cleaned_content = cleaned_content[:-3]
            cleaned_content = cleaned_content.strip()
            
            # Extract JSON array from the response
            start = cleaned_content.find("[")
            end = cleaned_content.rfind("]") + 1
            
            if start == -1 or end == 0:
                if self.debug:
                    print("[ai] No JSON array found in OpenAI response")
                    print(f"[ai] Response content: {cleaned_content[:200]}...")
                return findings
                
            json_str = cleaned_content[start:end]
            arr = json.loads(json_str)
            
            if not isinstance(arr, list):
                if self.debug:
                    print("[ai] Response is not a JSON array")
                return findings
            
            for item in arr:
                if not isinstance(item, dict):
                    continue
                    
                findings.append(AIFinding(
                    severity=item.get("severity", "medium").lower(),
                    title=item.get("title", "Unknown vulnerability"),
                    description=item.get("description", ""),
                    location=item.get("location", "Unknown"),
                    confidence=float(item.get("confidence", 0.5)),
                    reasoning=item.get("reasoning", ""),
                    suggested_fix=item.get("suggested_fix")
                ))
                
        except json.JSONDecodeError as e:
            if self.debug:
                print(f"[ai] JSON decode error: {e}")
                print(f"[ai] Attempted to parse: {content[:500]}...")
        except Exception as e:
            if self.debug:
                print(f"[ai] Failed to parse OpenAI response: {e}")
                print(f"[ai] Response: {content[:500]}...")
                import traceback
                traceback.print_exc()
        return findings

class PipelineManager:
    """Pipeline manager for smart contract analysis with SpoonOS integration"""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.logger = self._setup_logging()
        self.cache_dir = Path("~/.spoon-audit/cache").expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize pipeline configurations with SpoonOS support
        self.pipelines = {
            "fast": PipelineConfig(
                name="fast",
                description="Quick analysis for development",
                stages=["parse", "static_basic", "cache"],
                parallel_stages=True,
                timeout_seconds=60,
                max_workers=2,
                ai_models=[],
                static_tools=["solhint"],
                spoon_agent_type="react"
            ),
            "thorough": PipelineConfig(
                name="thorough",
                description="Comprehensive static and AI analysis",
                stages=["parse", "static_full", "ai_single", "correlate", "cache"],
                parallel_stages=True,
                timeout_seconds=300,
                max_workers=4,
                ai_models=["gpt-4"],
                static_tools=["slither", "mythril", "solhint"],
                spoon_agent_type="react"
            ),
            "ai-enhanced": PipelineConfig(
                name="ai-enhanced",
                description="Multi-model AI consensus with advanced correlation",
                stages=["parse", "static_full", "ai_consensus", "ml_analysis", "correlate", "cache"],
                parallel_stages=True,
                timeout_seconds=600,
                max_workers=6,
                ai_models=["gpt-4", "claude-3-sonnet", "llama-3.1-70b"],
                static_tools=["slither", "mythril", "solhint", "semgrep"],
                spoon_agent_type="react"
            ),
            "spoon-powered": PipelineConfig(
                name="spoon-powered",
                description="SpoonOS agent-driven analysis with MCP support",
                stages=["parse", "static_full", "spoon_analysis", "correlate", "cache"],
                parallel_stages=True,
                timeout_seconds=450,
                max_workers=4,
                ai_models=["claude-3-sonnet"],
                static_tools=["slither", "mythril", "solhint"],
                spoon_agent_type="spoon_react_mcp"
            ),
            "custom-agent": PipelineConfig(
                name="custom-agent",
                description="Custom SpoonOS contract agent with specialized tools",
                stages=["parse", "static_full", "custom_spoon_analysis", "correlate", "cache"],
                parallel_stages=True,
                timeout_seconds=400,
                max_workers=4,
                ai_models=["anthropic/claude-3-5-sonnet-20241022"],
                static_tools=["slither", "mythril", "solhint"],
                spoon_agent_type="custom"
            )
        }
        
        # Initialize ML components if available
        self.ml_analyzer = MLAnalyzer() if SKLEARN_AVAILABLE else None
        
        if debug:
            self.logger.debug(f"Pipeline Manager initialized with {len(self.pipelines)} pipelines")
            self.logger.debug(f"ML analysis available: {SKLEARN_AVAILABLE}")
            self.logger.debug(f"PyTorch available: {TORCH_AVAILABLE}")
            self.logger.debug(f"SpoonOS available: {SPOON_AVAILABLE}")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for pipeline manager"""
        logger = logging.getLogger("PipelineManager")
        logger.setLevel(logging.DEBUG if self.debug else logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    async def validate_paths(self, path: str) -> List[str]:
        """Validate and collect Solidity file paths"""
        self.logger.debug(f"Validating path: {path}")
        
        path_obj = Path(path)
        valid_paths = []
        
        if path_obj.is_file():
            if path_obj.suffix == '.sol':
                valid_paths.append(str(path_obj))
        elif path_obj.is_directory():
            # Recursively find .sol files
            for sol_file in path_obj.rglob("*.sol"):
                # Skip node_modules and other common exclusions
                if not any(part.startswith('.') or part in ['node_modules', 'build', 'dist'] 
                          for part in sol_file.parts):
                    valid_paths.append(str(sol_file))
        
        self.logger.debug(f"Found {len(valid_paths)} valid Solidity files")
        return valid_paths
    
    async def execute_pipeline(
        self, 
        pipeline_name: str, 
        contract_paths: List[str],
        custom_config: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Execute a complete analysis pipeline"""
        
        if pipeline_name not in self.pipelines:
            raise ValueError(f"Unknown pipeline: {pipeline_name}")
        
        config = self.pipelines[pipeline_name]
        self.logger.info(f"Executing pipeline: {config.name}")
        
        # Apply custom configuration
        if custom_config:
            config = self._merge_config(config, custom_config)
        
        start_time = time.time()
        results = {
            "pipeline": pipeline_name,
            "start_time": start_time,
            "config": config,
            "stages": {},
            "contracts": {},
            "summary": {}
        }
        
        try:
            # Execute pipeline stages sequentially or in parallel
            for stage in config.stages:
                stage_start = time.time()
                self.logger.debug(f"Executing stage: {stage}")
                
                stage_results = await self._execute_stage(
                    stage, contract_paths, config, results
                )
                
                results["stages"][stage] = {
                    "duration": time.time() - stage_start,
                    "results": stage_results,
                    "status": "completed"
                }
                
                self.logger.debug(f"Stage {stage} completed in {time.time() - stage_start:.2f}s")
            
            # Calculate final summary
            results["summary"] = self._calculate_pipeline_summary(results)
            results["total_duration"] = time.time() - start_time
            results["status"] = "completed"
            
            self.logger.info(f"Pipeline {pipeline_name} completed in {results['total_duration']:.2f}s")
            
        except Exception as e:
            results["status"] = "failed"
            results["error"] = str(e)
            results["total_duration"] = time.time() - start_time
            self.logger.error(f"Pipeline {pipeline_name} failed: {e}")
            raise
        
        return results
    
    async def _execute_stage(
        self, 
        stage: str, 
        contract_paths: List[str], 
        config: PipelineConfig,
        previous_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a specific pipeline stage"""
        
        if stage == "parse":
            return await self._stage_parse(contract_paths, config)
        elif stage == "static_basic":
            return await self._stage_static_basic(contract_paths, config, previous_results)
        elif stage == "static_full":
            return await self._stage_static_full(contract_paths, config, previous_results)
        elif stage == "ai_single":
            return await self._stage_ai_single(contract_paths, config, previous_results)
        elif stage == "ai_consensus":
            return await self._stage_ai_consensus(contract_paths, config, previous_results)
        elif stage == "spoon_analysis":
            return await self._stage_spoon_analysis(contract_paths, config, previous_results)
        elif stage == "custom_spoon_analysis":
            return await self._stage_custom_spoon_analysis(contract_paths, config, previous_results)
        elif stage == "ml_analysis":
            return await self._stage_ml_analysis(contract_paths, config, previous_results)
        elif stage == "correlate":
            return await self._stage_correlate(contract_paths, config, previous_results)
        elif stage == "cache":
            return await self._stage_cache(contract_paths, config, previous_results)
        else:
            raise ValueError(f"Unknown stage: {stage}")
    
    async def _stage_parse(self, contract_paths: List[str], config: PipelineConfig) -> Dict[str, Any]:
        """Parse all Solidity contracts"""
        results = {"parsed_contracts": {}, "errors": []}
        
        async def parse_contract(path: str) -> Tuple[str, Optional[ParsedContract], Optional[str]]:
            try:
                parser = SolidityParser(debug=self.debug)
                parsed = parser.parse_file(path)
                return path, parsed, None
            except Exception as e:
                return path, None, str(e)
        
        # Parse contracts in parallel
        tasks = [parse_contract(path) for path in contract_paths]
        parse_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in parse_results:
            if isinstance(result, Exception):
                results["errors"].append(f"Parse task failed: {result}")
                continue
                
            path, parsed, error = result
            if error:
                results["errors"].append(f"{path}: {error}")
            else:
                results["parsed_contracts"][path] = parsed
        
        self.logger.debug(f"Parsed {len(results['parsed_contracts'])} contracts with {len(results['errors'])} errors")
        return results
    
    async def _stage_static_basic(self, contract_paths: List[str], config: PipelineConfig, previous_results: Dict[str, Any]) -> Dict[str, Any]:
        """Run basic static analysis"""
        results = {"findings": {}, "tool_stats": {}}
        
        # Use only fast tools for basic analysis
        basic_tools = ["solhint"]
        
        for tool in basic_tools:
            try:
                scanner = StaticScanner(tools=[tool], debug=self.debug)
                tool_findings = {}
                
                for contract_path in contract_paths:
                    findings = scanner.scan(contract_path)
                    if findings:
                        tool_findings[contract_path] = findings.get(tool, [])
                
                results["findings"][tool] = tool_findings
                results["tool_stats"][tool] = {
                    "contracts_scanned": len(tool_findings),
                    "total_findings": sum(len(f) for f in tool_findings.values())
                }
                
            except Exception as e:
                self.logger.error(f"Static tool {tool} failed: {e}")
                results["tool_stats"][tool] = {"error": str(e)}
        
        return results
    
    async def _stage_static_full(self, contract_paths: List[str], config: PipelineConfig, previous_results: Dict[str, Any]) -> Dict[str, Any]:
        """Run comprehensive static analysis"""
        results = {"findings": {}, "tool_stats": {}, "correlation_matrix": {}}
        
        # Run all configured static tools
        if config.parallel_stages:
            # Parallel execution
            tasks = []
            for tool in config.static_tools:
                task = self._run_static_tool(tool, contract_paths)
                tasks.append(task)
            
            tool_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, tool in enumerate(config.static_tools):
                if isinstance(tool_results[i], Exception):
                    self.logger.error(f"Tool {tool} failed: {tool_results[i]}")
                    results["tool_stats"][tool] = {"error": str(tool_results[i])}
                else:
                    results["findings"][tool] = tool_results[i]["findings"]
                    results["tool_stats"][tool] = tool_results[i]["stats"]
        else:
            # Sequential execution
            for tool in config.static_tools:
                try:
                    tool_result = await self._run_static_tool(tool, contract_paths)
                    results["findings"][tool] = tool_result["findings"]
                    results["tool_stats"][tool] = tool_result["stats"]
                except Exception as e:
                    self.logger.error(f"Tool {tool} failed: {e}")
                    results["tool_stats"][tool] = {"error": str(e)}
        
        # Calculate tool correlation matrix
        results["correlation_matrix"] = self._calculate_tool_correlation(results["findings"])
        
        return results
    
    async def _run_static_tool(self, tool: str, contract_paths: List[str]) -> Dict[str, Any]:
        """Run a single static analysis tool"""
        scanner = StaticScanner(tools=[tool], debug=self.debug)
        findings = {}
        total_findings = 0
        
        for contract_path in contract_paths:
            try:
                result = scanner.scan(contract_path)
                contract_findings = result.get(tool, [])
                if contract_findings:
                    findings[contract_path] = contract_findings
                    total_findings += len(contract_findings)
            except Exception as e:
                self.logger.warning(f"Tool {tool} failed on {contract_path}: {e}")
                continue
        
        return {
            "findings": findings,
            "stats": {
                "contracts_scanned": len(contract_paths),
                "contracts_with_findings": len(findings),
                "total_findings": total_findings
            }
        }
    
    async def _stage_ai_single(self, contract_paths: List[str], config: PipelineConfig, previous_results: Dict[str, Any]) -> Dict[str, Any]:
        """Run single-model AI analysis"""
        results = {"findings": {}, "model_stats": {}}
        
        if not config.ai_models:
            return results
        
        # Use the first (primary) AI model
        primary_model = config.ai_models[0]
        
        try:
            ai_analyzer = AIAnalyzer(debug=self.debug)
            
            # Get parsed contracts from previous stage
            parsed_contracts = previous_results.get("stages", {}).get("parse", {}).get("results", {}).get("parsed_contracts", {})
            static_findings = previous_results.get("stages", {}).get("static_full", {}).get("results", {}).get("findings", {})
            
            for contract_path in contract_paths:
                if contract_path not in parsed_contracts:
                    continue
                
                try:
                    parsed = parsed_contracts[contract_path]
                    static_context = static_findings
                    
                    ai_findings = ai_analyzer.analyze(contract_path, parsed, static_context)
                    if ai_findings:
                        results["findings"][contract_path] = ai_findings
                
                except Exception as e:
                    self.logger.warning(f"AI analysis failed for {contract_path}: {e}")
                    continue
            
            results["model_stats"][primary_model] = {
                "contracts_analyzed": len([p for p in contract_paths if p in parsed_contracts]),
                "contracts_with_findings": len(results["findings"]),
                "total_findings": sum(len(f) for f in results["findings"].values())
            }
            
        except Exception as e:
            self.logger.error(f"AI model {primary_model} failed: {e}")
            results["model_stats"][primary_model] = {"error": str(e)}
        
        return results
    
    async def _stage_ai_consensus(self, contract_paths: List[str], config: PipelineConfig, previous_results: Dict[str, Any]) -> Dict[str, Any]:
        """Run multi-model AI consensus analysis"""
        results = {"findings": {}, "model_stats": {}, "consensus_stats": {}}
        
        if len(config.ai_models) < 2:
            # Fall back to single model
            return await self._stage_ai_single(contract_paths, config, previous_results)
        
        # Get context from previous stages
        parsed_contracts = previous_results.get("stages", {}).get("parse", {}).get("results", {}).get("parsed_contracts", {})
        static_findings = previous_results.get("stages", {}).get("static_full", {}).get("results", {}).get("findings", {})
        
        # Run analysis with each model
        model_results = {}
        
        for model in config.ai_models:
            try:
                ai_analyzer = AIAnalyzer(debug=self.debug)
                
                model_findings = {}
                for contract_path in contract_paths:
                    if contract_path not in parsed_contracts:
                        continue
                    
                    try:
                        parsed = parsed_contracts[contract_path]
                        findings = ai_analyzer.analyze(contract_path, parsed, static_findings)
                        if findings:
                            model_findings[contract_path] = findings
                    except Exception as e:
                        self.logger.warning(f"Model {model} failed on {contract_path}: {e}")
                        continue
                
                model_results[model] = model_findings
                results["model_stats"][model] = {
                    "contracts_analyzed": len([p for p in contract_paths if p in parsed_contracts]),
                    "contracts_with_findings": len(model_findings),
                    "total_findings": sum(len(f) for f in model_findings.values())
                }
                
            except Exception as e:
                self.logger.error(f"AI model {model} failed: {e}")
                results["model_stats"][model] = {"error": str(e)}
        
        # Apply consensus algorithm
        consensus_findings = self._apply_advanced_consensus(model_results, config.ai_models)
        results["findings"] = consensus_findings
        
        # Calculate consensus statistics
        results["consensus_stats"] = self._calculate_consensus_stats(model_results, consensus_findings)
        
        return results
    
    async def _stage_spoon_analysis(self, contract_paths: List[str], config: PipelineConfig, previous_results: Dict[str, Any]) -> Dict[str, Any]:
        """Run SpoonOS agent analysis"""
        results = {"findings": {}, "agent_stats": {}}
        
        if not SPOON_AVAILABLE:
            self.logger.warning("SpoonOS not available - skipping SpoonOS analysis")
            return results
        
        try:
            ai_analyzer = AIAnalyzer(
                debug=self.debug, 
                use_spoon_agent=True, 
                spoon_agent_type=config.spoon_agent_type
            )
            
            # Get parsed contracts from previous stage
            parsed_contracts = previous_results.get("stages", {}).get("parse", {}).get("results", {}).get("parsed_contracts", {})
            static_findings = previous_results.get("stages", {}).get("static_full", {}).get("results", {}).get("findings", {})
            
            for contract_path in contract_paths:
                if contract_path not in parsed_contracts:
                    continue
                
                try:
                    parsed = parsed_contracts[contract_path]
                    spoon_findings = ai_analyzer.analyze(contract_path, parsed, static_findings)
                    if spoon_findings:
                        results["findings"][contract_path] = spoon_findings
                
                except Exception as e:
                    self.logger.warning(f"SpoonOS analysis failed for {contract_path}: {e}")
                    continue
            
            results["agent_stats"] = {
                "agent_type": config.spoon_agent_type,
                "contracts_analyzed": len([p for p in contract_paths if p in parsed_contracts]),
                "contracts_with_findings": len(results["findings"]),
                "total_findings": sum(len(f) for f in results["findings"].values())
            }
            
        except Exception as e:
            self.logger.error(f"SpoonOS agent failed: {e}")
            results["agent_stats"] = {"error": str(e)}
        
        return results
    
    async def _stage_custom_spoon_analysis(self, contract_paths: List[str], config: PipelineConfig, previous_results: Dict[str, Any]) -> Dict[str, Any]:
        """Run custom SpoonOS contract agent analysis"""
        results = {"findings": {}, "agent_stats": {}}
        
        if not SPOON_AVAILABLE:
            self.logger.warning("SpoonOS not available - skipping custom SpoonOS analysis")
            return results
        
        try:
            ai_analyzer = AIAnalyzer(
                debug=self.debug, 
                use_spoon_agent=True, 
                spoon_agent_type="custom"
            )
            
            # Get parsed contracts from previous stage
            parsed_contracts = previous_results.get("stages", {}).get("parse", {}).get("results", {}).get("parsed_contracts", {})
            static_findings = previous_results.get("stages", {}).get("static_full", {}).get("results", {}).get("findings", {})
            
            for contract_path in contract_paths:
                if contract_path not in parsed_contracts:
                    continue
                
                try:
                    parsed = parsed_contracts[contract_path]
                    custom_findings = ai_analyzer.analyze(contract_path, parsed, static_findings)
                    if custom_findings:
                        results["findings"][contract_path] = custom_findings
                
                except Exception as e:
                    self.logger.warning(f"Custom SpoonOS analysis failed for {contract_path}: {e}")
                    continue
            
            results["agent_stats"] = {
                "agent_type": "custom_contract_agent",
                "contracts_analyzed": len([p for p in contract_paths if p in parsed_contracts]),
                "contracts_with_findings": len(results["findings"]),
                "total_findings": sum(len(f) for f in results["findings"].values())
            }
            
        except Exception as e:
            self.logger.error(f"Custom SpoonOS agent failed: {e}")
            results["agent_stats"] = {"error": str(e)}
        
        return results
    
    async def _stage_ml_analysis(self, contract_paths: List[str], config: PipelineConfig, previous_results: Dict[str, Any]) -> Dict[str, Any]:
        """Run machine learning analysis for pattern detection"""
        results = {"patterns": {}, "clusters": {}, "anomalies": {}}
        
        if not self.ml_analyzer:
            self.logger.warning("ML analysis not available - sklearn not installed")
            return results
        
        try:
            # Collect all findings for ML analysis
            all_findings = []
            finding_metadata = []
            
            # Get findings from previous stages
            static_results = previous_results.get("stages", {}).get("static_full", {}).get("results", {}).get("findings", {})
            
            # Check for different AI analysis stages
            ai_results = {}
            if "ai_consensus" in previous_results.get("stages", {}):
                ai_results = previous_results["stages"]["ai_consensus"]["results"].get("findings", {})
            elif "spoon_analysis" in previous_results.get("stages", {}):
                ai_results = previous_results["stages"]["spoon_analysis"]["results"].get("findings", {})
            elif "custom_spoon_analysis" in previous_results.get("stages", {}):
                ai_results = previous_results["stages"]["custom_spoon_analysis"]["results"].get("findings", {})
            elif "ai_single" in previous_results.get("stages", {}):
                ai_results = previous_results["stages"]["ai_single"]["results"].get("findings", {})
            
            # Prepare data for ML analysis
            for contract_path in contract_paths:
                # Static findings
                for tool, tool_findings in static_results.items():
                    contract_findings = tool_findings.get(contract_path, [])
                    for finding in contract_findings:
                        all_findings.append(f"{finding.title} {getattr(finding, 'description', '')}")
                        finding_metadata.append({
                            "contract": contract_path,
                            "tool": tool,
                            "type": "static",
                            "severity": finding.severity
                        })
                
                # AI findings
                contract_ai_findings = ai_results.get(contract_path, [])
                for finding in contract_ai_findings:
                    all_findings.append(f"{finding.title} {finding.description}")
                    finding_metadata.append({
                        "contract": contract_path,
                        "tool": "ai",
                        "type": "ai",
                        "severity": finding.severity
                    })
            
            if len(all_findings) < 5:  # Need minimum findings for ML
                self.logger.warning("Insufficient findings for ML analysis")
                return results
            
            # Run ML analysis
            ml_results = self.ml_analyzer.analyze_patterns(all_findings, finding_metadata)
            results.update(ml_results)
            
        except Exception as e:
            self.logger.error(f"ML analysis failed: {e}")
            results["error"] = str(e)
        
        return results
    
    async def _stage_correlate(self, contract_paths: List[str], config: PipelineConfig, previous_results: Dict[str, Any]) -> Dict[str, Any]:
        """Correlate findings across different analysis methods"""
        results = {"correlations": {}, "deduplicated_findings": {}, "confidence_scores": {}}
        
        try:
            # Collect all findings
            static_findings = previous_results.get("stages", {}).get("static_full", {}).get("results", {}).get("findings", {})
            
            # Get AI findings from appropriate stage
            ai_findings = {}
            stage_priority = ["custom_spoon_analysis", "spoon_analysis", "ai_consensus", "ai_single"]
            for stage in stage_priority:
                if stage in previous_results.get("stages", {}):
                    ai_findings = previous_results["stages"][stage]["results"].get("findings", {})
                    break
            
            correlation_engine = FindingCorrelationEngine(debug=self.debug)
            
            for contract_path in contract_paths:
                # Get findings for this contract
                contract_static = {}
                for tool, tool_findings in static_findings.items():
                    if contract_path in tool_findings:
                        contract_static[tool] = tool_findings[contract_path]
                
                contract_ai = ai_findings.get(contract_path, [])
                
                # Run correlation analysis
                correlation_result = correlation_engine.correlate_findings(
                    contract_static, contract_ai, contract_path
                )
                
                results["correlations"][contract_path] = correlation_result["correlations"]
                results["deduplicated_findings"][contract_path] = correlation_result["deduplicated"]
                results["confidence_scores"][contract_path] = correlation_result["confidence_scores"]
            
        except Exception as e:
            self.logger.error(f"Correlation analysis failed: {e}")
            results["error"] = str(e)
        
        return results
    
    async def _stage_cache(self, contract_paths: List[str], config: PipelineConfig, previous_results: Dict[str, Any]) -> Dict[str, Any]:
        """Cache results for future use"""
        results = {"cached_files": [], "cache_stats": {}}
        
        try:
            cache_manager = CacheManager(self.cache_dir, debug=self.debug)
            
            for contract_path in contract_paths:
                # Generate cache key based on contract content and config
                cache_key = cache_manager.generate_cache_key(contract_path, config)
                
                # Cache the results for this contract
                contract_results = self._extract_contract_results(contract_path, previous_results)
                
                if contract_results:
                    cache_file = cache_manager.save_to_cache(cache_key, contract_results)
                    results["cached_files"].append(cache_file)
            
            results["cache_stats"] = {
                "files_cached": len(results["cached_files"]),
                "cache_directory": str(self.cache_dir),
                "total_cache_size": cache_manager.get_cache_size()
            }
            
        except Exception as e:
            self.logger.error(f"Cache operation failed: {e}")
            results["error"] = str(e)
        
        return results
    
    def _apply_advanced_consensus(self, model_results: Dict[str, Dict[str, List]], ai_models: List[str]) -> Dict[str, List]:
        """Apply advanced consensus algorithm with weighted voting"""
        consensus_findings = {}
        
        # Model weights (can be configured based on model performance)
        model_weights = {
            "gpt-4": 0.4,
            "claude-3-sonnet": 0.35,
            "llama-3.1-70b": 0.25
        }
        
        # Get all unique contracts
        all_contracts = set()
        for model_findings in model_results.values():
            all_contracts.update(model_findings.keys())
        
        for contract_path in all_contracts:
            contract_consensus = []
            
            # Group similar findings across models
            finding_groups = {}
            
            for model, model_findings in model_results.items():
                if contract_path not in model_findings:
                    continue
                
                for finding in model_findings[contract_path]:
                    # Create signature for grouping
                    signature = self._create_finding_signature(finding)
                    
                    if signature not in finding_groups:
                        finding_groups[signature] = []
                    
                    finding_groups[signature].append({
                        "model": model,
                        "finding": finding,
                        "weight": model_weights.get(model, 0.33)
                    })
            
            # Apply consensus rules
            for signature, group in finding_groups.items():
                total_weight = sum(item["weight"] for item in group)
                avg_confidence = sum(item["finding"].confidence * item["weight"] for item in group) / total_weight
                
                # Consensus threshold: either multiple models agree OR single model with high confidence
                if len(group) >= 2 or (len(group) == 1 and avg_confidence > 0.85):
                    # Take the highest confidence finding as representative
                    best_finding = max(group, key=lambda x: x["finding"].confidence * x["weight"])["finding"]
                    
                    # Update confidence based on consensus
                    consensus_finding = AIFinding(
                        severity=best_finding.severity,
                        title=best_finding.title,
                        description=best_finding.description,
                        location=best_finding.location,
                        confidence=min(avg_confidence * (1 + (len(group) - 1) * 0.1), 1.0),  # Boost for consensus
                        reasoning=f"Consensus from {len(group)} model(s). {best_finding.reasoning}",
                        suggested_fix=best_finding.suggested_fix
                    )
                    
                    contract_consensus.append(consensus_finding)
            
            if contract_consensus:
                consensus_findings[contract_path] = contract_consensus
        
        return consensus_findings
    
    def _create_finding_signature(self, finding) -> str:
        """Create a signature for finding grouping"""
        # Normalize title and location for comparison
        title_normalized = finding.title.lower().replace(" ", "").replace("-", "").replace("_", "")
        severity_part = finding.severity
        
        # Create hash of normalized components
        signature_text = f"{severity_part}:{title_normalized}"
        return hashlib.md5(signature_text.encode()).hexdigest()[:12]
    
    def _calculate_tool_correlation(self, tool_findings: Dict[str, Dict[str, List]]) -> Dict[str, Dict[str, float]]:
        """Calculate correlation matrix between static analysis tools"""
        tools = list(tool_findings.keys())
        correlation_matrix = {}
        
        for tool1 in tools:
            correlation_matrix[tool1] = {}
            for tool2 in tools:
                if tool1 == tool2:
                    correlation_matrix[tool1][tool2] = 1.0
                else:
                    # Calculate Jaccard similarity between tool findings
                    correlation = self._calculate_jaccard_similarity(
                        tool_findings[tool1], tool_findings[tool2]
                    )
                    correlation_matrix[tool1][tool2] = correlation
        
        return correlation_matrix
    
    def _calculate_jaccard_similarity(self, findings1: Dict[str, List], findings2: Dict[str, List]) -> float:
        """Calculate Jaccard similarity between two sets of findings"""
        # Create sets of finding signatures
        set1 = set()
        set2 = set()
        
        for contract_findings in findings1.values():
            for finding in contract_findings:
                set1.add(self._create_finding_signature(finding))
        
        for contract_findings in findings2.values():
            for finding in contract_findings:
                set2.add(self._create_finding_signature(finding))
        
        if not set1 and not set2:
            return 1.0
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        return intersection / union if union > 0 else 0.0
    
    def _calculate_consensus_stats(self, model_results: Dict, consensus_findings: Dict) -> Dict[str, Any]:
        """Calculate statistics about the consensus process"""
        stats = {
            "models_used": len(model_results),
            "total_model_findings": 0,
            "consensus_findings": 0,
            "agreement_rate": 0.0,
            "model_contributions": {}
        }
        
        # Count total findings from all models
        for model, model_findings in model_results.items():
            model_count = sum(len(findings) for findings in model_findings.values())
            stats["total_model_findings"] += model_count
            stats["model_contributions"][model] = model_count
        
        # Count consensus findings
        stats["consensus_findings"] = sum(len(findings) for findings in consensus_findings.values())
        
        # Calculate agreement rate
        if stats["total_model_findings"] > 0:
            stats["agreement_rate"] = stats["consensus_findings"] / stats["total_model_findings"]
        
        return stats
    
    def _calculate_pipeline_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate summary statistics for the entire pipeline"""
        summary = {
            "total_stages": len(results["stages"]),
            "successful_stages": len([s for s in results["stages"].values() if s["status"] == "completed"]),
            "total_findings": 0,
            "findings_by_type": {},
            "risk_assessment": "low"
        }
        
        # Count findings from all stages
        for stage_name, stage_data in results["stages"].items():
            stage_results = stage_data.get("results", {})
            
            if "findings" in stage_results:
                findings = stage_results["findings"]
                if isinstance(findings, dict):
                    for tool_or_contract, tool_findings in findings.items():
                        if isinstance(tool_findings, dict):
                            # Tool -> Contract -> Findings structure
                            for contract_findings in tool_findings.values():
                                if isinstance(contract_findings, list):
                                    summary["total_findings"] += len(contract_findings)
                        elif isinstance(tool_findings, list):
                            # Contract -> Findings structure
                            summary["total_findings"] += len(tool_findings)
        
        # Determine risk assessment based on findings
        if summary["total_findings"] > 10:
            summary["risk_assessment"] = "high"
        elif summary["total_findings"] > 5:
            summary["risk_assessment"] = "medium"
        
        return summary
    
    def _extract_contract_results(self, contract_path: str, all_results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract results specific to a single contract"""
        contract_results = {
            "contract_path": contract_path,
            "findings": {},
            "metadata": {}
        }
        
        # Extract findings from each stage
        for stage_name, stage_data in all_results.get("stages", {}).items():
            stage_results = stage_data.get("results", {})
            
            if "findings" in stage_results:
                findings = stage_results["findings"]
                contract_results["findings"][stage_name] = self._extract_contract_findings(
                    contract_path, findings
                )
        
        return contract_results
    
    def _extract_contract_findings(self, contract_path: str, findings: Dict) -> List:
        """Extract findings for a specific contract from various finding structures"""
        contract_findings = []
        
        if isinstance(findings, dict):
            for key, value in findings.items():
                if key == contract_path and isinstance(value, list):
                    contract_findings.extend(value)
                elif isinstance(value, dict) and contract_path in value:
                    if isinstance(value[contract_path], list):
                        contract_findings.extend(value[contract_path])
        
        return contract_findings
    
    def _merge_config(self, base_config: PipelineConfig, custom_config: Dict[str, Any]) -> PipelineConfig:
        """Merge custom configuration with base pipeline configuration"""
        # Create a copy of the base config
        merged_config = PipelineConfig(
            name=base_config.name,
            description=base_config.description,
            stages=base_config.stages.copy(),
            parallel_stages=base_config.parallel_stages,
            cache_enabled=base_config.cache_enabled,
            timeout_seconds=base_config.timeout_seconds,
            max_workers=base_config.max_workers,
            ai_models=base_config.ai_models.copy() if base_config.ai_models else [],
            static_tools=base_config.static_tools.copy() if base_config.static_tools else [],
            spoon_agent_type=base_config.spoon_agent_type
        )
        
        # Apply custom configuration
        for key, value in custom_config.items():
            if hasattr(merged_config, key):
                setattr(merged_config, key, value)
        
        return merged_config


class MLAnalyzer:
    """Machine Learning analyzer for pattern detection in findings"""
    
    def __init__(self):
        if not SKLEARN_AVAILABLE:
            raise ImportError("scikit-learn required for ML analysis")
        
        self.vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
        self.cluster_model = KMeans(n_clusters=5, random_state=42)
    
    def analyze_patterns(self, findings_text: List[str], metadata: List[Dict]) -> Dict[str, Any]:
        """Analyze patterns in findings using ML techniques"""
        if len(findings_text) < 5:
            return {"error": "Insufficient data for ML analysis"}
        
        try:
            # Vectorize findings text
            X = self.vectorizer.fit_transform(findings_text)
            
            # Cluster findings
            clusters = self.cluster_model.fit_predict(X)
            
            # Analyze clusters
            cluster_analysis = self._analyze_clusters(clusters, findings_text, metadata)
            
            # Detect anomalies (findings that don't fit well in any cluster)
            anomalies = self._detect_anomalies(X, clusters)
            
            return {
                "clusters": cluster_analysis,
                "anomalies": anomalies,
                "feature_importance": self._get_feature_importance(),
                "total_patterns": len(set(clusters))
            }
            
        except Exception as e:
            return {"error": f"ML analysis failed: {str(e)}"}
    
    def _analyze_clusters(self, clusters: 'np.ndarray', findings_text: List[str], metadata: List[Dict]) -> Dict[str, Any]:
        """Analyze the characteristics of each cluster"""
        cluster_analysis = {}
        
        for cluster_id in set(clusters):
            cluster_indices = [i for i, c in enumerate(clusters) if c == cluster_id]
            cluster_findings = [findings_text[i] for i in cluster_indices]
            cluster_metadata = [metadata[i] for i in cluster_indices]
            
            # Analyze cluster characteristics
            severities = [m['severity'] for m in cluster_metadata]
            tools = [m['tool'] for m in cluster_metadata]
            contracts = [m['contract'] for m in cluster_metadata]
            
            cluster_analysis[f"cluster_{cluster_id}"] = {
                "size": len(cluster_findings),
                "dominant_severity": max(set(severities), key=severities.count),
                "dominant_tool": max(set(tools), key=tools.count),
                "affected_contracts": len(set(contracts)),
                "sample_findings": cluster_findings[:3]  # Sample findings
            }
        
        return cluster_analysis
    
    def _detect_anomalies(self, X, clusters: 'np.ndarray') -> List[int]:
        """Detect anomalous findings that don't fit well in clusters"""
        # Calculate distances to cluster centers
        cluster_centers = self.cluster_model.cluster_centers_
        distances = []
        
        for i, cluster_id in enumerate(clusters):
            center = cluster_centers[cluster_id]
            # Convert sparse matrix to dense for distance calculation
            x_dense = X[i].toarray().flatten()
            distance = np.linalg.norm(x_dense - center)
            distances.append(distance)
        
        # Find outliers (findings far from their cluster center)
        threshold = np.percentile(distances, 95)  # Top 5% as anomalies
        anomalies = [i for i, d in enumerate(distances) if d > threshold]
        
        return anomalies
    
    def _get_feature_importance(self) -> List[Tuple[str, float]]:
        """Get the most important features (terms) from the analysis"""
        feature_names = self.vectorizer.get_feature_names_out()
        
        # Get cluster centers to determine important features
        cluster_centers = self.cluster_model.cluster_centers_
        
        # Calculate feature importance as max absolute value across clusters
        importance_scores = np.max(np.abs(cluster_centers), axis=0)
        
        # Get top features
        top_indices = np.argsort(importance_scores)[-20:]  # Top 20 features
        top_features = [(feature_names[i], importance_scores[i]) for i in top_indices]
        
        return sorted(top_features, key=lambda x: x[1], reverse=True)


class FindingCorrelationEngine:
    """Engine for correlating findings across different analysis methods"""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.similarity_threshold = 0.7
    
    def correlate_findings(self, static_findings: Dict[str, List], ai_findings: List, contract_path: str) -> Dict[str, Any]:
        """Correlate static and AI findings for a contract"""
        
        # Flatten static findings
        all_static = []
        for tool_findings in static_findings.values():
            all_static.extend(tool_findings)
        
        # Find correlations
        correlations = []
        deduplicated = []
        confidence_scores = {}
        
        # Track which findings have been matched
        matched_static = set()
        matched_ai = set()
        
        # Correlate AI findings with static findings
        for i, ai_finding in enumerate(ai_findings):
            best_match = None
            best_similarity = 0
            
            for j, static_finding in enumerate(all_static):
                if j in matched_static:
                    continue
                
                similarity = self._calculate_finding_similarity(ai_finding, static_finding)
                if similarity > best_similarity and similarity > self.similarity_threshold:
                    best_similarity = similarity
                    best_match = j
            
            if best_match is not None:
                # Found correlation
                static_finding = all_static[best_match]
                correlations.append({
                    "ai_finding": i,
                    "static_finding": best_match,
                    "similarity": best_similarity,
                    "correlation_type": "direct_match"
                })
                
                # Create deduplicated finding with enhanced confidence
                enhanced_finding = self._create_enhanced_finding(ai_finding, static_finding, best_similarity)
                deduplicated.append(enhanced_finding)
                confidence_scores[len(deduplicated) - 1] = enhanced_finding.confidence
                
                matched_static.add(best_match)
                matched_ai.add(i)
        
        # Add unmatched AI findings
        for i, ai_finding in enumerate(ai_findings):
            if i not in matched_ai:
                deduplicated.append(ai_finding)
                confidence_scores[len(deduplicated) - 1] = ai_finding.confidence
        
        # Add unmatched static findings
        for j, static_finding in enumerate(all_static):
            if j not in matched_static:
                # Convert static finding to AI finding format for consistency
                ai_format_finding = AIFinding(
                    severity=static_finding.severity,
                    title=static_finding.title,
                    description=getattr(static_finding, 'description', ''),
                    location=static_finding.location,
                    confidence=getattr(static_finding, 'confidence', 0.8),
                    reasoning=f"Static analysis by {getattr(static_finding, 'tool', 'unknown')}",
                    suggested_fix=getattr(static_finding, 'suggested_fix', None)
                )
                deduplicated.append(ai_format_finding)
                confidence_scores[len(deduplicated) - 1] = ai_format_finding.confidence
        
        return {
            "correlations": correlations,
            "deduplicated": deduplicated,
            "confidence_scores": confidence_scores,
            "correlation_stats": {
                "total_static": len(all_static),
                "total_ai": len(ai_findings),
                "correlations_found": len(correlations),
                "correlation_rate": len(correlations) / max(len(ai_findings), 1)
            }
        }
    
    def _calculate_finding_similarity(self, ai_finding, static_finding) -> float:
        """Calculate similarity between AI and static findings"""
        # Title similarity
        title_similarity = self._text_similarity(ai_finding.title, static_finding.title)
        
        # Location similarity
        location_similarity = self._location_similarity(ai_finding.location, static_finding.location)
        
        # Severity similarity
        severity_similarity = 1.0 if ai_finding.severity == static_finding.severity else 0.5
        
        # Description similarity (if available)
        description_similarity = 0.0
        ai_desc = getattr(ai_finding, 'description', '')
        static_desc = getattr(static_finding, 'description', '')
        if ai_desc and static_desc:
            description_similarity = self._text_similarity(ai_desc, static_desc)
        
        # Weighted combination
        weights = [0.4, 0.3, 0.2, 0.1]  # title, location, severity, description
        similarities = [title_similarity, location_similarity, severity_similarity, description_similarity]
        
        return sum(w * s for w, s in zip(weights, similarities))
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using simple token overlap"""
        if not text1 or not text2:
            return 0.0
        
        # Tokenize and normalize
        tokens1 = set(text1.lower().split())
        tokens2 = set(text2.lower().split())
        
        # Jaccard similarity
        intersection = len(tokens1.intersection(tokens2))
        union = len(tokens1.union(tokens2))
        
        return intersection / union if union > 0 else 0.0
    
    def _location_similarity(self, loc1: str, loc2: str) -> float:
        """Calculate location similarity"""
        if not loc1 or not loc2:
            return 0.0
        
        # Extract file names and line numbers if present
        def parse_location(loc):
            parts = loc.split(':')
            file_part = parts[0] if parts else ''
            line_part = parts[1] if len(parts) > 1 else ''
            return file_part.split('/')[-1], line_part  # Get just filename
        
        file1, line1 = parse_location(loc1)
        file2, line2 = parse_location(loc2)
        
        # File similarity
        file_sim = 1.0 if file1 == file2 else 0.0
        
        # Line similarity (if both have line numbers)
        line_sim = 0.0
        if line1 and line2 and line1.isdigit() and line2.isdigit():
            line_diff = abs(int(line1) - int(line2))
            line_sim = max(0, 1.0 - line_diff / 100.0)  # Decay with distance
        
        return 0.7 * file_sim + 0.3 * line_sim
    
    def _create_enhanced_finding(self, ai_finding, static_finding, similarity: float):
        """Create an enhanced finding by combining AI and static analysis results"""
        # Boost confidence based on correlation
        base_confidence = ai_finding.confidence
        correlation_boost = similarity * 0.2  # Up to 20% boost
        enhanced_confidence = min(base_confidence + correlation_boost, 1.0)
        
        # Combine descriptions
        ai_desc = ai_finding.description
        static_desc = getattr(static_finding, 'description', '')
        static_tool = getattr(static_finding, 'tool', 'static analysis')
        
        combined_description = ai_desc
        if static_desc and static_desc not in ai_desc:
            combined_description += f" (Also detected by {static_tool}: {static_desc})"
        
        # Enhanced reasoning
        enhanced_reasoning = ai_finding.reasoning + f" This finding is corroborated by {static_tool} with {similarity:.0%} similarity."
        
        return AIFinding(
            severity=ai_finding.severity,
            title=ai_finding.title,
            description=combined_description,
            location=ai_finding.location,
            confidence=enhanced_confidence,
            reasoning=enhanced_reasoning,
            suggested_fix=ai_finding.suggested_fix
        )


class CacheManager:
    """Manages caching of analysis results"""
    
    def __init__(self, cache_dir: Path, debug: bool = False):
        self.cache_dir = cache_dir
        self.debug = debug
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_cache_key(self, contract_path: str, config: PipelineConfig) -> str:
        """Generate a cache key based on contract content and configuration"""
        try:
            # Read contract content
            with open(contract_path, 'r') as f:
                content = f.read()
            
            # Create hash of content + config
            config_str = f"{config.name}:{','.join(config.static_tools)}:{','.join(config.ai_models or [])}:{config.spoon_agent_type}"
            combined = f"{content}:{config_str}"
            
            return hashlib.sha256(combined.encode()).hexdigest()[:16]
            
        except Exception as e:
            if self.debug:
                print(f"Cache key generation failed: {e}")
            # Fallback to simple hash
            return hashlib.md5(f"{contract_path}:{config.name}".encode()).hexdigest()[:16]
    
    def save_to_cache(self, cache_key: str, data: Dict[str, Any]) -> str:
        """Save data to cache"""
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        try:
            cache_data = {
                "timestamp": time.time(),
                "cache_key": cache_key,
                "data": data
            }
            
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2, default=str)
            
            return str(cache_file)
            
        except Exception as e:
            if self.debug:
                print(f"Cache save failed: {e}")
            return ""
    
    def load_from_cache(self, cache_key: str, max_age_hours: int = 24) -> Optional[Dict[str, Any]]:
        """Load data from cache if it exists and is not expired"""
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Check if cache is expired
            cache_age = time.time() - cache_data.get("timestamp", 0)
            if cache_age > max_age_hours * 3600:
                if self.debug:
                    print(f"Cache expired for key {cache_key}")
                return None
            
            return cache_data.get("data")
            
        except Exception as e:
            if self.debug:
                print(f"Cache load failed: {e}")
            return None
    
    def get_cache_size(self) -> int:
        """Get total cache size in bytes"""
        total_size = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                total_size += cache_file.stat().st_size
            except:
                continue
        return total_size
    
    def cleanup_cache(self, max_age_days: int = 7) -> int:
        """Clean up old cache files"""
        cleaned_count = 0
        cutoff_time = time.time() - (max_age_days * 24 * 3600)
        
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                if cache_file.stat().st_mtime < cutoff_time:
                    cache_file.unlink()
                    cleaned_count += 1
            except:
                continue
        
        return cleaned_count


# Pipeline execution helper functions
def create_pipeline_manager(debug: bool = False) -> PipelineManager:
    """Factory function to create a pipeline manager"""
    return PipelineManager(debug=debug)


def get_available_pipelines() -> Dict[str, str]:
    """Get available pipeline configurations"""
    return {
        "fast": "Quick analysis for development",
        "thorough": "Comprehensive static and AI analysis",
        "ai-enhanced": "Multi-model AI consensus with advanced correlation",
        "spoon-powered": "SpoonOS agent-driven analysis with MCP support",
        "custom-agent": "Custom SpoonOS contract agent with specialized tools"
    }


async def run_pipeline_analysis(
    contract_paths: List[str],
    pipeline_name: str = "thorough",
    custom_config: Dict[str, Any] = None,
    debug: bool = False
) -> Dict[str, Any]:
    """
    Convenience function to run a complete pipeline analysis
    
    Args:
        contract_paths: List of paths to Solidity contracts
        pipeline_name: Name of the pipeline to run
        custom_config: Optional custom configuration overrides
        debug: Enable debug mode
    
    Returns:
        Dictionary containing analysis results
    """
    manager = create_pipeline_manager(debug=debug)
    
    # Validate paths
    validated_paths = []
    for path in contract_paths:
        paths = await manager.validate_paths(path)
        validated_paths.extend(paths)
    
    if not validated_paths:
        raise ValueError("No valid Solidity files found")
    
    # Execute pipeline
    results = await manager.execute_pipeline(
        pipeline_name=pipeline_name,
        contract_paths=validated_paths,
        custom_config=custom_config
    )
    
    return results


# SpoonOS-specific convenience functions
async def run_spoon_analysis(
    contract_paths: List[str],
    agent_type: str = "react",
    debug: bool = False
) -> Dict[str, Any]:
    """
    Run analysis using SpoonOS agents
    
    Args:
        contract_paths: List of contract paths
        agent_type: Type of SpoonOS agent ("react", "spoon_react_mcp", "custom")
        debug: Enable debug mode
    
    Returns:
        Analysis results
    """
    pipeline_map = {
        "react": "spoon-powered",
        "spoon_react_mcp": "spoon-powered", 
        "custom": "custom-agent"
    }
    
    pipeline = pipeline_map.get(agent_type, "spoon-powered")
    custom_config = {"spoon_agent_type": agent_type}
    
    return await run_pipeline_analysis(
        contract_paths=contract_paths,
        pipeline_name=pipeline,
        custom_config=custom_config,
        debug=debug
    )


def setup_spoon_environment():
    """Setup SpoonOS environment variables and configuration"""
    required_vars = {
        "SPOON_API_KEY": "SpoonOS API key or OpenAI key for OpenRouter",
        "SPOON_MODEL": "Model name (default: anthropic/claude-3-5-sonnet-20241022)",
        "SPOON_BASE_URL": "Base URL (default: https://openrouter.ai/api/v1)"
    }
    
    missing_vars = []
    for var, desc in required_vars.items():
        if not os.getenv(var):
            missing_vars.append(f"{var}: {desc}")
    
    if missing_vars:
        print("SpoonOS Environment Setup Required:")
        print("=" * 50)
        for var in missing_vars:
            print(f"- {var}")
        print("\nSet these environment variables to enable SpoonOS integration.")
        return False
    
    return True


# Example usage and testing functions
async def test_spoon_integration():
    """Test SpoonOS integration"""
    # Create test contract
    test_contract = """
    pragma solidity ^0.8.0;
    
    contract VulnerableContract {
        mapping(address => uint256) public balances;
        
        function withdraw(uint256 amount) public {
            require(balances[msg.sender] >= amount, "Insufficient balance");
            (bool success, ) = msg.sender.call{value: amount}("");
            require(success, "Transfer failed");
            balances[msg.sender] -= amount;  // State change after external call - reentrancy!
        }
        
        function deposit() public payable {
            balances[msg.sender] += msg.value;
        }
    }
    """
    
    # Write test contract to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sol', delete=False) as f:
        f.write(test_contract)
        temp_path = f.name
    
    try:
        print("=== Testing SpoonOS Integration ===")
        
        # Check SpoonOS environment
        if not setup_spoon_environment():
            print("Skipping SpoonOS tests - environment not configured")
            return
        
        # Test different SpoonOS pipelines
        spoon_pipelines = ["spoon-powered", "custom-agent"]
        
        for pipeline in spoon_pipelines:
            if not SPOON_AVAILABLE:
                print(f"Skipping {pipeline} - SpoonOS not available")
                continue
                
            print(f"\n--- Testing {pipeline} pipeline ---")
            
            try:
                results = await run_pipeline_analysis(
                    contract_paths=[temp_path],
                    pipeline_name=pipeline,
                    debug=True
                )
                
                print(f"Pipeline: {results['pipeline']}")
                print(f"Status: {results['status']}")
                print(f"Duration: {results['total_duration']:.2f}s")
                print(f"Total findings: {results['summary']['total_findings']}")
                
                # Show SpoonOS-specific results
                spoon_stages = ["spoon_analysis", "custom_spoon_analysis"]
                for stage in spoon_stages:
                    if stage in results.get("stages", {}):
                        stage_data = results["stages"][stage]["results"]
                        agent_stats = stage_data.get("agent_stats", {})
                        print(f"Agent type: {agent_stats.get('agent_type', 'unknown')}")
                        print(f"Agent findings: {agent_stats.get('total_findings', 0)}")
                        break
                
            except Exception as e:
                print(f"Pipeline {pipeline} failed: {e}")
                if "debug=True" in str(e):
                    import traceback
                    traceback.print_exc()
        
        # Test direct SpoonOS analysis
        print(f"\n--- Testing direct SpoonOS analysis ---")
        
        for agent_type in ["react", "custom"]:
            try:
                print(f"Testing {agent_type} agent...")
                results = await run_spoon_analysis(
                    contract_paths=[temp_path],
                    agent_type=agent_type,
                    debug=True
                )
                print(f"Direct SpoonOS analysis completed: {results['summary']['total_findings']} findings")
            except Exception as e:
                print(f"Direct analysis with {agent_type} failed: {e}")
    
    finally:
        # Clean up temp file
        import os
        os.unlink(temp_path)


async def test_pipeline_manager():
    """Test function for pipeline manager including SpoonOS integration"""
    # Create test contract
    test_contract = """
    pragma solidity ^0.8.0;
    
    contract VulnerableContract {
        mapping(address => uint256) public balances;
        
        function withdraw(uint256 amount) public {
            require(balances[msg.sender] >= amount, "Insufficient balance");
            (bool success, ) = msg.sender.call{value: amount}("");
            require(success, "Transfer failed");
            balances[msg.sender] -= amount;  // State change after external call - reentrancy!
        }
        
        function deposit() public payable {
            balances[msg.sender] += msg.value;
        }
    }
    """
    
    # Write test contract to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sol', delete=False) as f:
        f.write(test_contract)
        temp_path = f.name
    
    try:
        # Test all available pipelines
        available_pipelines = get_available_pipelines()
        print("=== Available Pipelines ===")
        for name, desc in available_pipelines.items():
            print(f"- {name}: {desc}")
        
        # Test standard pipelines
        standard_pipelines = ["fast", "thorough"]
        
        for pipeline in standard_pipelines:
            print(f"\n=== Testing {pipeline} pipeline ===")
            
            results = await run_pipeline_analysis(
                contract_paths=[temp_path],
                pipeline_name=pipeline,
                debug=True
            )
            
            print(f"Pipeline: {results['pipeline']}")
            print(f"Status: {results['status']}")
            print(f"Duration: {results['total_duration']:.2f}s")
            print(f"Stages completed: {results['summary']['successful_stages']}/{results['summary']['total_stages']}")
            print(f"Total findings: {results['summary']['total_findings']}")
            print(f"Risk assessment: {results['summary']['risk_assessment']}")
        
        # Test SpoonOS integration if available
        if SPOON_AVAILABLE:
            await test_spoon_integration()
        else:
            print("\n=== SpoonOS Integration ===")
            print("SpoonOS not available - install spoon_ai to enable agent integration")
            
    finally:
        # Clean up temp file
        import os
        os.unlink(temp_path)


if __name__ == "__main__":
    # Run tests if this file is executed directly
    import asyncio
    asyncio.run(test_pipeline_manager())