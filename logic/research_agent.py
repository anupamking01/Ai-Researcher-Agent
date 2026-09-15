# Description: Research assistant class that handles the research process for a given question.

import asyncio
import json
import os
import uuid

from agent.llm_utils import UsageTracker
from logic import prompts
from logic.experiment import ExperimentConfig, normalize_verifier_output
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
        usage_tracker=None,
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
        self.usage_tracker = usage_tracker or UsageTracker()

        # Run instrumentation used by the paper trace logger.
        self.search_queries = []
        self.search_call_count = 0
        self.search_records = []
        self.scheduled_urls = []
        self.successful_urls = []
        self.failed_urls = []
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
            usage_tracker=self.usage_tracker,
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
            self.scheduled_urls.append(url)
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
            usage_tracker=self.usage_tracker,
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
        if len(queries) != 4:
            raise ValueError(
                f"Planner must return exactly 4 usable queries; got {len(queries)}"
            )

        await self._log(
            "🧠 Planned research queries: " + json.dumps(queries, ensure_ascii=False)
        )
        return queries

    async def async_search(self, query, max_sources):
        """Search and browse unseen sources for one query under a fixed budget."""
        allowed = min(max(int(max_sources), 0), self.remaining_source_budget)
        if allowed <= 0:
            return []

        # Ask the search engine for more candidates than we browse so duplicate
        # URLs across planner queries do not unnecessarily leave the fixed
        # browse budget unused. Only scheduled browse calls consume the budget.
        candidate_limit = min(
            max(
                allowed * self.experiment_config.search_candidate_multiplier,
                allowed,
            ),
            20,
        )
        self.search_call_count += 1
        try:
            raw_results = web_search(query, num_results=candidate_limit)
            search_results = json.loads(raw_results)
        except RuntimeError as exc:
            # A transient metasearch outage should not abort the whole agent
            # before later planned queries are attempted. The artifact validator
            # still rejects a final run that fails to spend the frozen source
            # budget, so this improves resilience without hiding under-retrieval.
            self.search_records.append(
                {
                    "query": query,
                    "candidate_urls": [],
                    "scheduled_urls": [],
                    "search_error": str(exc)[:1000],
                }
            )
            await self._log(
                f"⚠️ Search failed for query '{query}': {type(exc).__name__}"
            )
            return []

        candidate_urls = [
            result.get("href")
            for result in search_results
            if isinstance(result, dict) and result.get("href")
        ]
        new_search_urls = await self.get_new_urls(candidate_urls, limit=allowed)
        self.search_records.append(
            {
                "query": query,
                "candidate_urls": candidate_urls,
                "scheduled_urls": list(new_search_urls),
            }
        )

        await self._log(
            "🌐 Browsing the following sites for relevant information: "
            f"{new_search_urls}..."
        )
        if not new_search_urls:
            return []

        # Count calls when scheduled, not only when successful. This keeps the
        # experimental tool budget comparable even when websites fail.
        self.browse_attempt_count += len(new_search_urls)

        # Limit only concurrent Selenium/Chrome renderers. Once a page's text is
        # captured, async_browse releases the semaphore and browser before doing
        # LLM summarization, preserving source-summary concurrency while avoiding
        # the renderer exhaustion seen on GitHub-hosted runners.
        browser_semaphore = asyncio.Semaphore(
            self.experiment_config.max_concurrent_browses
        )

        async def browse_one(url):
            return await asyncio.wait_for(
                async_browse(
                    url,
                    query,
                    self.websocket,
                    usage_tracker=self.usage_tracker,
                    raise_on_error=True,
                    browser_semaphore=browser_semaphore,
                ),
                timeout=self.experiment_config.browse_timeout_seconds,
            )

        tasks = [browse_one(url) for url in new_search_urls]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        successful_responses = []
        for url, response in zip(new_search_urls, responses):
            if isinstance(response, Exception) or not response:
                self.browse_failure_count += 1
                self.failed_urls.append(url)
                if isinstance(response, asyncio.TimeoutError):
                    failure_name = "browse_timeout"
                else:
                    failure_name = (
                        type(response).__name__
                        if isinstance(response, Exception)
                        else "empty_response"
                    )
                await self._log(f"⚠️ Could not browse {url}: {failure_name}")
                continue

            self.browse_success_count += 1
            self.successful_urls.append(url)
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
            result = normalize_verifier_output(raw_result)
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
        verification_path = f"./outputs/{self.directory_name}/verification.json"
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
        await self._log(
            f"I will research based on the following concepts: {result}\n"
        )
        return json.loads(result)

    async def write_report(self, report_type, websocket):
        """Write/export the final report and optionally verify factual support."""
        report_type_func = prompts.get_report_by_type(report_type)
        await self._log(
            f"✍️ Writing {report_type} for research task: {self.question}..."
        )
        report_prompt = report_type_func(self.question, self.research_summary)

        if self.experiment_config.stream_report:
            answer_awaitable = await self.call_agent(
                report_prompt,
                stream=True,
                websocket=websocket,
            )
            report_text = await answer_awaitable
        else:
            # Pilot runs are deliberately non-streaming so the pinned OpenAI
            # client returns its provider-reported token usage object.
            report_text = await self.call_agent(report_prompt, stream=False)

        path = None
        try:
            path = await write_md_to_pdf(
                report_type,
                self.directory_name,
                report_text,
            )
        except Exception as exc:
            # PDF rendering is not part of the experimental treatment. Preserve
            # the generated report as Markdown instead of invalidating the run.
            md_path = f"./outputs/{self.directory_name}/{report_type}.md"
            os.makedirs(os.path.dirname(md_path), exist_ok=True)
            write_to_file(md_path, report_text)
            path = md_path
            await self._log(
                f"⚠️ PDF export failed ({type(exc).__name__}); saved Markdown report."
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
