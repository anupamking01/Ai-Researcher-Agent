# Description: Research assistant class that handles the research process for a given question.

import asyncio
import json
import os
import uuid

from logic import prompts
from logic.experiment import ExperimentConfig
from scrape.web_search import web_search
from scrape.web_scrape import async_browse
from settings import Config
from text_preprocess.text import (
    create_chat_completion,
    create_message,
    read_txt_files,
    write_md_to_pdf,
    write_to_file,
)


CFG = Config()


class ResearchAgent:
    def __init__(
        self,
        question,
        agent,
        agent_role_prompt,
        websocket,
        experiment_config=None,
    ):
        """Initialize the research assistant for a single research task."""
        self.question = question
        self.agent = agent
        self.agent_role_prompt = (
            agent_role_prompt
            if agent_role_prompt
            else prompts.generate_agent_role_prompt(agent)
        )
        self.visited_urls = set()
        self.research_summary = ""
        self.directory_name = uuid.uuid4()
        self.dir_path = os.path.dirname(f"./outputs/{self.directory_name}/")
        self.websocket = websocket
        self.experiment_config = experiment_config or ExperimentConfig()

        # Run instrumentation used by the paper trace logger.
        self.search_queries = []
        self.browse_attempt_count = 0
        self.browse_success_count = 0
        self.browse_failure_count = 0
        self.verification_result = None

    async def _log(self, output):
        if self.websocket is not None and hasattr(self.websocket, "send_json"):
            await self.websocket.send_json({"type": "logs", "output": output})

    async def summarize(self, text, topic):
        """Summarize text with respect to the requested topic."""
        messages = [create_message(text, topic)]
        await self._log(f"📝 Summarizing text for query: {topic}")
        return create_chat_completion(
            model=CFG.fast_llm_model,
            messages=messages,
        )

    @property
    def remaining_source_budget(self):
        return max(
            self.experiment_config.source_budget - self.browse_attempt_count,
            0,
        )

    @staticmethod
    def _allocate_source_budgets(total_budget, n_queries):
        """Spread a fixed browsing budget as evenly as possible across queries."""
        if n_queries <= 0:
            return []
        base, remainder = divmod(total_budget, n_queries)
        return [base + (1 if index < remainder else 0) for index in range(n_queries)]

    async def get_new_urls(self, url_set_input, limit):
        """Return unseen URLs while preserving order and respecting a call budget."""
        allowed = min(max(int(limit), 0), self.remaining_source_budget)
        if allowed <= 0:
            return []

        new_urls = []
        for url in url_set_input:
            if len(new_urls) >= allowed:
                break
            if not url or url in self.visited_urls:
                continue
            self.visited_urls.add(url)
            new_urls.append(url)
            await self._log(f"✅ Scheduling source URL for research: {url}\n")
        return new_urls

    async def call_agent(self, action, stream=False, websocket=None):
        messages = [
            {"role": "system", "content": self.agent_role_prompt},
            {"role": "user", "content": action},
        ]
        return create_chat_completion(
            model=CFG.smart_llm_model,
            messages=messages,
            stream=stream,
            websocket=websocket,
        )

    async def create_search_queries(self):
        """Create focused search queries for the research question."""
        if self.experiment_config.planning_mode == "direct":
            return [self.question]

        result = await self.call_agent(
            prompts.generate_search_queries_prompt(self.question)
        )
        try:
            parsed = json.loads(result)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(
                "Planner did not return the required JSON list of queries"
            ) from exc

        if not isinstance(parsed, list):
            raise ValueError("Planner output must be a JSON list")
        queries = [str(query).strip() for query in parsed if str(query).strip()]
        if not queries:
            raise ValueError("Planner returned no usable search queries")

        await self._log(
            "🧠 Planned research queries: " + json.dumps(queries, ensure_ascii=False)
        )
        return queries

    async def async_search(self, query, max_sources):
        """Search and browse unseen sources for one query under a fixed budget.

        Individual browse failures are logged and excluded instead of causing
        the entire research run to fail when responses are aggregated.
        """
        allowed = min(max(int(max_sources), 0), self.remaining_source_budget)
        if allowed <= 0:
            return []

        search_results = json.loads(web_search(query, num_results=allowed))
        candidate_urls = [
            result.get("href")
            for result in search_results
            if isinstance(result, dict) and result.get("href")
        ]
        new_search_urls = await self.get_new_urls(candidate_urls, limit=allowed)

        await self._log(
            "🌐 Browsing the following sites for relevant information: "
            f"{new_search_urls}..."
        )
        if not new_search_urls:
            return []

        # Count calls when scheduled, not only when successful. This keeps the
        # experimental tool budget comparable even when websites fail.
        self.browse_attempt_count += len(new_search_urls)

        tasks = [
            async_browse(url, query, self.websocket) for url in new_search_urls
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        successful_responses = []
        for url, response in zip(new_search_urls, responses):
            if isinstance(response, Exception) or not response:
                self.browse_failure_count += 1
                failure_name = (
                    type(response).__name__
                    if isinstance(response, Exception)
                    else "empty_response"
                )
                await self._log(f"⚠️ Could not browse {url}: {failure_name}")
                continue

            self.browse_success_count += 1
            successful_responses.append(str(response))

        return successful_responses

    async def run_search_summary(self, query, max_sources, query_index):
        """Run retrieval for a query and persist the gathered source text."""
        await self._log(
            f"🔎 Running research for '{query}' with budget {max_sources}..."
        )
        responses = await self.async_search(query, max_sources=max_sources)
        result = "\n".join(responses)

        output_path = (
            f"./outputs/{self.directory_name}/research-query-{query_index:02d}.txt"
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        write_to_file(output_path, result)
        return result

    async def conduct_research(self):
        """Collect source-grounded research context for the question."""
        self.research_summary = (
            read_txt_files(self.dir_path) if os.path.isdir(self.dir_path) else ""
        )

        if not self.research_summary:
            self.search_queries = await self.create_search_queries()
            per_query_budgets = self._allocate_source_budgets(
                self.experiment_config.source_budget,
                len(self.search_queries),
            )

            for index, (query, query_budget) in enumerate(
                zip(self.search_queries, per_query_budgets),
                start=1,
            ):
                if query_budget <= 0 or self.remaining_source_budget <= 0:
                    continue
                research_result = await self.run_search_summary(
                    query,
                    max_sources=query_budget,
                    query_index=index,
                )
                if research_result:
                    self.research_summary += f"{research_result}\n\n"

        await self._log(
            "Research summary: "
            f"{len(self.research_summary.split())} words, "
            f"{self.browse_attempt_count} browse attempts, "
            f"{self.browse_success_count} successful sources."
        )
        return self.research_summary

    @staticmethod
    def _parse_verification_json(raw_result):
        """Parse and normalize the bounded verifier response."""
        text = (raw_result or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()

        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Verifier output must be a JSON object")

        labels = (
            "supported",
            "partially_supported",
            "unsupported",
            "contradicted",
        )
        normalized = {}
        for label in labels:
            value = int(data.get(label, 0))
            normalized[label] = max(value, 0)

        normalized["claims_checked"] = sum(normalized[label] for label in labels)
        examples = data.get("examples", [])
        normalized["examples"] = examples[:8] if isinstance(examples, list) else []
        return normalized

    async def verify_report(self, report_text):
        """Run the paper's first claim-to-evidence verifier without repair."""
        raw_result = await self.call_agent(
            prompts.generate_verification_prompt(
                self.question,
                report_text,
                self.research_summary,
            )
        )
        try:
            result = self._parse_verification_json(raw_result)
            result["status"] = "ok"
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            result = {
                "status": "parse_error",
                "claims_checked": 0,
                "supported": 0,
                "partially_supported": 0,
                "unsupported": 0,
                "contradicted": 0,
                "examples": [],
                "error": type(exc).__name__,
            }

        self.verification_result = result
        verification_path = (
            f"./outputs/{self.directory_name}/verification.json"
        )
        os.makedirs(os.path.dirname(verification_path), exist_ok=True)
        write_to_file(
            verification_path,
            json.dumps(result, indent=2, ensure_ascii=False),
        )
        return result

    async def create_concepts(self):
        """Create important concepts from the accumulated research context."""
        result = await self.call_agent(
            prompts.generate_concepts_prompt(
                self.question,
                self.research_summary,
            )
        )
        await self._log(f"I will research based on the following concepts: {result}\n")
        return json.loads(result)

    async def write_report(self, report_type, websocket):
        """Write/export the final report and optionally verify factual support."""
        report_type_func = prompts.get_report_by_type(report_type)
        await self._log(
            f"✍️ Writing {report_type} for research task: {self.question}..."
        )
        answer_awaitable = await self.call_agent(
            report_type_func(self.question, self.research_summary),
            stream=True,
            websocket=websocket,
        )
        report_text = await answer_awaitable

        path = await write_md_to_pdf(
            report_type,
            self.directory_name,
            report_text,
        )

        if self.experiment_config.verification_mode == "verify":
            await self._log("🔬 Verifying report claims against retrieved evidence...")
            await self.verify_report(report_text)

        return report_text, path

    async def write_lessons(self):
        """Write lessons on concepts extracted from the research."""
        concepts = await self.create_concepts()
        for concept in concepts:
            answer = await self.call_agent(
                prompts.generate_lesson_prompt(concept),
                stream=True,
                websocket=self.websocket,
            )
            await write_md_to_pdf("Lesson", self.directory_name, await answer)
