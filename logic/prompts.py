def generate_agent_role_prompt(agent):
    """Generate the system role prompt for a named research agent."""
    prompts = {
        "Finance Agent": "You are a seasoned finance analyst AI assistant. Your primary goal is to compose comprehensive, astute, impartial, and methodically arranged financial reports based on provided data and trends.",
        "Travel Agent": "You are a world-travelled AI tour guide assistant. Your main purpose is to draft engaging, insightful, unbiased, and well-structured travel reports on given locations, including history, attractions, and cultural insights.",
        "Academic Research Agent": "You are an AI academic research assistant. Your primary responsibility is to create thorough, academically rigorous, unbiased, and systematically organized reports on a given research topic, following the standards of scholarly work.",
        "Business Analyst": "You are an experienced AI business analyst assistant. Your main objective is to produce comprehensive, insightful, impartial, and systematically structured business reports based on provided business data, market trends, and strategic analysis.",
        "Computer Security Analyst Agent": "You are an AI specializing in computer security analysis. Your principal duty is to generate comprehensive, meticulously detailed, impartial, and systematically structured reports on computer security topics. This includes Exploits, Techniques, Threat Actors, and Advanced Persistent Threat (APT) Groups. All produced reports should adhere to the highest standards of scholarly work and provide in-depth insights into the complexities of computer security.",
        "Default Agent": "You are an AI critical thinker research assistant. Your sole purpose is to write well written, critically acclaimed, objective and structured reports on given text.",
    }
    return prompts.get(agent, "No such agent")


def generate_report_prompt(question, research_summary):
    """Generate the final research-report prompt."""
    return (
        f'"""{research_summary}""" Using the above information, answer the following '
        f'question or topic: "{question}" in a detailed report -- '
        "The report should focus on the answer to the question, should be well structured, informative, "
        "in depth, with facts and numbers if available, a minimum of 1,200 words and with markdown syntax and APA format. "
        "You MUST determine your own concrete and valid opinion based on the information found. Do NOT defer to general and meaningless conclusions. "
        "Write all source URLs at the end of the report in APA format."
    )


def generate_search_queries_prompt(question):
    """Generate a fixed four-query planner prompt for controlled experiments."""
    return (
        "Write 4 web search queries that together support an objective, multi-source answer "
        f'to the following research question: "{question}". '
        "Return only a JSON-compatible list of strings in exactly this format: "
        '["query 1", "query 2", "query 3", "query 4"]'
    )


def generate_verification_prompt(question, report, research_summary, max_claims=20):
    """Generate a bounded claim-to-evidence verification prompt.

    ``max_claims`` defaults to 20 for the in-treatment P6V verifier. The common
    post-hoc evaluator uses a lower predeclared cap to control evaluation cost
    while applying the identical rubric to every treatment variant.
    """
    max_claims = int(max_claims)
    if max_claims <= 0:
        raise ValueError("max_claims must be positive")
    return f"""
You are evaluating factual support in a generated web-research report.

Research question:
{question}

Generated report:
--- REPORT START ---
{report}
--- REPORT END ---

Retrieved evidence available to the writer:
--- EVIDENCE START ---
{research_summary}
--- EVIDENCE END ---

Instructions:
1. Identify up to {max_claims} important atomic factual claims from the report. Ignore purely subjective recommendations, headings, and rhetorical statements.
2. For each selected claim, compare it only with the evidence above. Do not use outside knowledge.
3. Label each claim exactly one of: supported, partially_supported, unsupported, contradicted.
4. Return ONLY valid JSON; do not wrap it in Markdown.
5. Use this exact top-level schema:
{{
  "claims_checked": <integer>,
  "supported": <integer>,
  "partially_supported": <integer>,
  "unsupported": <integer>,
  "contradicted": <integer>,
  "examples": [
    {{"claim": "...", "label": "supported|partially_supported|unsupported|contradicted", "reason": "brief evidence-based reason"}}
  ]
}}
6. The four label counts must sum to claims_checked. Keep examples to at most 8 representative claims.
""".strip()


def generate_resource_report_prompt(question, research_summary):
    """Generate a bibliography/recommendation report prompt."""
    return (
        f'"""{research_summary}""" Based on the above information, generate a bibliography recommendation report for the following '
        f'question or topic: "{question}". The report should provide a detailed analysis of each recommended resource, '
        "explaining how each source can contribute to finding answers to the research question. "
        "Focus on the relevance, reliability, and significance of each source. "
        "Ensure that the report is well-structured, informative, in-depth, and follows Markdown syntax. "
        "Include relevant facts, figures, and numbers whenever available. The report should have a minimum length of 1,200 words."
    )


def generate_outline_report_prompt(question, research_summary):
    """Generate a structured research-report outline prompt."""
    return (
        f'"""{research_summary}""" Using the above information, generate an outline for a research report in Markdown syntax '
        f'for the following question or topic: "{question}". The outline should provide a well-structured framework '
        "for the research report, including the main sections, subsections, and key points to be covered. "
        "The research report should be detailed, informative, in-depth, and a minimum of 1,200 words."
    )


def generate_concepts_prompt(question, research_summary):
    """Generate five concepts to learn from the accumulated evidence."""
    return (
        f'"""{research_summary}""" Using the above information, generate a list of 5 main concepts to learn for a research report '
        f'on the following question or topic: "{question}". '
        'Return only a list of strings in this format: ["concept 1", "concept 2", "concept 3", "concept 4", "concept 5"]'
    )


def generate_lesson_prompt(concept):
    """Generate a lesson prompt for one extracted concept."""
    return (
        f"Generate a comprehensive lesson about {concept} in Markdown syntax. This should include the definition "
        f"of {concept}, its historical background and development, its applications or uses in different "
        f"fields, and notable events or facts related to {concept}."
    )


def get_report_by_type(report_type):
    report_type_mapping = {
        "research_report": generate_report_prompt,
        "resource_report": generate_resource_report_prompt,
        "outline_report": generate_outline_report_prompt,
    }
    return report_type_mapping[report_type]


def auto_agent_instructions():
    return """
        This task involves researching a given topic, regardless of its complexity or the availability of a definitive answer. The research is conducted by a specific agent, defined by its type and role, with each agent requiring distinct instructions.
        Agent
        The agent is determined by the field of the topic and the specific name of the agent that could be utilized to research the topic provided. Agents are categorized by their area of expertise, and each agent type is associated with a corresponding emoji.

        examples:
        task: "should I invest in apple stocks?"
        response:
        {
            "agent": "Finance Agent",
            "agent_role_prompt": "You are a seasoned finance analyst AI assistant."
        }
        task: "could reselling sneakers become profitable?"
        response:
        {
            "agent": "Business Analyst",
            "agent_role_prompt": "You are an experienced AI business analyst assistant."
        }
        task: "what are the most interesting sites in Tel Aviv?"
        response:
        {
            "agent": "Travel Agent",
            "agent_role_prompt": "You are a world-travelled AI tour guide assistant."
        }
    """