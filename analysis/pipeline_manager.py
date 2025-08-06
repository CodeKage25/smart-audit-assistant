"""
Enhanced Pipeline Manager for Smart Contract Analysis
Handles orchestration of multiple analysis tools and AI models
"""

import os
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from rich.console import Console

console = Console()

@dataclass
class PipelineConfig:
    """Configuration for analysis pipeline"""
    parallel_execution: bool = True
    cache_enabled: bool = True
    timeout_seconds: int = 300
    max_concurrent_tools: int = 3
    retry_attempts: int = 2

class PipelineManager:
    """
    Manages the analysis pipeline orchestration
    """
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.config = PipelineConfig()
        self.console = Console()
        
        if self.debug:
            self.console.log("[yellow]PipelineManager initialized with debug mode[/yellow]")
    
    async def validate_paths(self, path: str) -> List[str]:
        """
        Validate and collect all Solidity files from the given path
        
        Args:
            path: File path or directory path
            
        Returns:
            List of valid Solidity file paths
        """
        validated_paths = []
        path_obj = Path(path)
        
        if not path_obj.exists():
            if self.debug:
                console.log(f"[red]Path does not exist: {path}[/red]")
            return []
        
        if path_obj.is_file():
            if path_obj.suffix == '.sol':
                validated_paths.append(str(path_obj))
                if self.debug:
                    console.log(f"[green]Added single file: {path_obj}[/green]")
            else:
                if self.debug:
                    console.log(f"[yellow]File is not a Solidity file: {path_obj}[/yellow]")
        
        elif path_obj.is_dir():
            # Recursively find all .sol files
            sol_files = list(path_obj.rglob("*.sol"))
            
            # Filter out node_modules and other common exclude directories
            exclude_dirs = {'node_modules', '.git', 'build', 'dist', 'out', 'artifacts', 'cache'}
            
            for sol_file in sol_files:
                # Check if any parent directory is in exclude list
                if not any(part in exclude_dirs for part in sol_file.parts):
                    validated_paths.append(str(sol_file))
                    if self.debug:
                        console.log(f"[green]Added directory file: {sol_file}[/green]")
                elif self.debug:
                    console.log(f"[yellow]Excluded file: {sol_file}[/yellow]")
        
        if self.debug:
            console.log(f"[blue]Total validated paths: {len(validated_paths)}[/blue]")
        
        return validated_paths
    
    def should_use_parallel(self, tool_count: int, file_count: int) -> bool:
        """
        Determine if parallel execution should be used based on workload
        
        Args:
            tool_count: Number of analysis tools
            file_count: Number of files to analyze
            
        Returns:
            True if parallel execution is recommended
        """
        if not self.config.parallel_execution:
            return False
        
        # Use parallel if we have multiple tools OR multiple files
        # But not if the workload is too small to benefit from parallelism
        if tool_count > 1 and file_count >= 1:
            return True
        elif file_count > 2 and tool_count >= 1:
            return True
        
        return False
    
    async def execute_with_timeout(self, coro, timeout: int = None) -> Any:
        """
        Execute a coroutine with timeout handling
        
        Args:
            coro: Coroutine to execute
            timeout: Timeout in seconds (uses config default if None)
            
        Returns:
            Result of the coroutine execution
            
        Raises:
            asyncio.TimeoutError: If execution exceeds timeout
        """
        if timeout is None:
            timeout = self.config.timeout_seconds
        
        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            if self.debug:
                console.log(f"[red]Operation timed out after {timeout} seconds[/red]")
            raise
    
    def get_cache_key(self, file_path: str, tool: str, file_hash: str = None) -> str:
        """
        Generate cache key for analysis results
        
        Args:
            file_path: Path to the analyzed file
            tool: Name of the analysis tool
            file_hash: Hash of the file content (optional)
            
        Returns:
            Cache key string
        """
        if file_hash is None:
            # Generate simple hash based on file modification time
            try:
                stat = os.stat(file_path)
                file_hash = str(int(stat.st_mtime))
            except (OSError, IOError):
                file_hash = "unknown"
        
        return f"{tool}:{Path(file_path).name}:{file_hash}"
    
    def is_cache_valid(self, cache_key: str) -> bool:
        """
        Check if cached results are still valid
        
        Args:
            cache_key: Cache key to check
            
        Returns:
            True if cache is valid and can be used
        """
        if not self.config.cache_enabled:
            return False
        
        # TODO: Implement actual cache validation logic
        # For now, always return False (no caching)
        return False
    
    def get_cached_result(self, cache_key: str) -> Optional[Any]:
        """
        Retrieve cached analysis result
        
        Args:
            cache_key: Cache key for the result
            
        Returns:
            Cached result if available, None otherwise
        """
        if not self.config.cache_enabled:
            return None
        
        # TODO: Implement actual cache retrieval
        return None
    
    def cache_result(self, cache_key: str, result: Any) -> bool:
        """
        Cache analysis result
        
        Args:
            cache_key: Cache key for storing the result
            result: Result to cache
            
        Returns:
            True if successfully cached
        """
        if not self.config.cache_enabled:
            return False
        
        # TODO: Implement actual cache storage
        if self.debug:
            console.log(f"[blue]Would cache result for key: {cache_key}[/blue]")
        
        return True
    
    async def run_tool_with_retry(self, tool_func, *args, **kwargs) -> Any:
        """
        Run a tool function with retry logic
        
        Args:
            tool_func: Function to execute
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            Result of the tool execution
            
        Raises:
            Exception: If all retry attempts fail
        """
        last_exception = None
        
        for attempt in range(self.config.retry_attempts + 1):
            try:
                if self.debug and attempt > 0:
                    console.log(f"[yellow]Retry attempt {attempt} for tool function[/yellow]")
                
                # If it's an async function, await it
                if asyncio.iscoroutinefunction(tool_func):
                    result = await tool_func(*args, **kwargs)
                else:
                    result = tool_func(*args, **kwargs)
                
                return result
                
            except Exception as e:
                last_exception = e
                if self.debug:
                    console.log(f"[red]Tool execution failed (attempt {attempt + 1}): {e}[/red]")
                
                if attempt < self.config.retry_attempts:
                    # Wait before retrying (exponential backoff)
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                else:
                    # Final attempt failed
                    break
        
        # All attempts failed
        if last_exception:
            raise last_exception
        else:
            raise Exception("Tool execution failed after all retry attempts")
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """
        Get current pipeline statistics and configuration
        
        Returns:
            Dictionary containing pipeline stats
        """
        return {
            "config": {
                "parallel_execution": self.config.parallel_execution,
                "cache_enabled": self.config.cache_enabled,
                "timeout_seconds": self.config.timeout_seconds,
                "max_concurrent_tools": self.config.max_concurrent_tools,
                "retry_attempts": self.config.retry_attempts
            },
            "debug_mode": self.debug
        }
    
    def optimize_pipeline_config(self, file_count: int, tool_count: int) -> None:
        """
        Optimize pipeline configuration based on workload
        
        Args:
            file_count: Number of files to analyze
            tool_count: Number of tools to run
        """
        # Adjust concurrent tools based on workload
        if file_count * tool_count > 10:
            self.config.max_concurrent_tools = min(4, tool_count)
        elif file_count * tool_count > 5:
            self.config.max_concurrent_tools = min(3, tool_count)
        else:
            self.config.max_concurrent_tools = min(2, tool_count)
        
        # Adjust timeout based on workload
        base_timeout = 60  # 1 minute base
        self.config.timeout_seconds = base_timeout + (file_count * tool_count * 10)
        
        if self.debug:
            console.log(f"[blue]Optimized config - Max concurrent: {self.config.max_concurrent_tools}, "
                       f"Timeout: {self.config.timeout_seconds}s[/blue]")