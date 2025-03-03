import streamlit as st
import os
import re
from groq import Groq
from langgraph.graph import StateGraph
from typing import TypedDict, Optional, List
from fpdf import FPDF

# ---- Sidebar Configuration ----
st.sidebar.title("Groq Cloud Settings")
api_key = st.sidebar.text_input("Groq Cloud API Key", type="password")
st.sidebar.markdown(
    """
    ## About this app
    This app generates detailed study notes and a quiz from an uploaded transcript using the GroqCloud API.
    Simply enter your Groq Cloud API key, upload a transcript file, and click the generate button.
    """
)
transcript_file = st.sidebar.file_uploader("Upload Transcript", type=["txt"])

# ---- Create Groq Client if API Key is provided ----
if api_key.strip():
    client = Groq(api_key=api_key)
else:
    st.sidebar.warning("Please enter a valid Groq Cloud API key to use the app.")
    st.stop()

# ---- Initialize Session State ----
if 'qna_bank' not in st.session_state:
    st.session_state.qna_bank = []
if 'study_notes' not in st.session_state:
    st.session_state.study_notes = ""
if 'user_answers' not in st.session_state:
    st.session_state.user_answers = {}
if 'show_quiz' not in st.session_state:
    st.session_state.show_quiz = False
if 'topic' not in st.session_state:
    st.session_state.topic = None
if 'key_concepts' not in st.session_state:
    st.session_state.key_concepts = None

# ---- Define State Schema ----
class QuizState(TypedDict):
    transcription: str
    topic: Optional[str]
    key_concepts: Optional[str]
    summarized_transcript: Optional[str]
    study_notes: Optional[str]
    questions: Optional[List[dict]]

# ---- Markdown Cleaning Function for Study Notes ----
def clean_markdown(text: str) -> str:
    """Remove common Markdown formatting markers from text."""
    text = re.sub(r'(?m)^#{1,6}\s*', '', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'(?m)^[\-\+\*]\s+', '', text)
    return text

# ---- PDF Conversion Function ----
def create_pdf(content: str, title: str = "Document") -> bytes:
    pdf = FPDF()
    pdf.add_page()
    # Add a Unicode-capable version of Helvetica.
    # Ensure "Helvetica.ttf" is available in the working directory or adjust the path accordingly.
    pdf.add_font("Helvetica", "", "Helvetica.ttf", uni=True)
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, txt=title, ln=1, align="C")
    pdf.ln(10)
    pdf.multi_cell(0, 10, content)
    # Output PDF and encode using 'latin1'
    pdf_output = pdf.output(dest="S").encode("latin1")
    return pdf_output

# ---- AI Agent Calls ----
class QuizAgents:
    def _call_llm(self, prompt, system_message):
        """Send request to GroqCloud API using the Groq Python SDK."""
        try:
            response = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.5,
                max_tokens=1500
            )
            return response.choices[0].message.content
        except Exception as e:
            st.error(f"API Error: {str(e)}")
            return None

    def classify_topic(self, state: QuizState) -> QuizState:
        """Determines the core topic of the transcript."""
        transcription = state["transcription"]
        system_msg = (
            "Analyze the given transcript and determine its primary academic or technical subject. "
            "Provide only the subject name, such as 'Machine Learning', 'Biology', 'Finance', etc."
        )
        topic = self._call_llm(transcription[:3000], system_msg)
        if not topic:
            st.error("Failed to classify topic. Please try again.")
            st.stop()
        state["topic"] = topic
        return state

    def extract_key_concepts(self, state: QuizState) -> QuizState:
        """Extracts key concepts, methodologies, and important terms from the transcript."""
        transcription = state["transcription"]
        topic = state["topic"]
        system_msg = (
            f"Extract key concepts, methodologies, technical terms, and important examples from the following {topic} lecture transcript. "
            "Organize them into clear categories such as 'Key Concepts', 'Methodologies', 'Important Terms', and 'Examples'. "
            "Provide concise explanations for each item where applicable. Ensure the output is well-structured and easy to follow."
            "Ignore session logistics, greetings, general chatter, off-topic questions, student joining counts, session breaks, or unrelated discussions. "
        )
        key_concepts = self._call_llm(transcription[:3000], system_msg)
        if not key_concepts:
            st.error("Failed to extract key concepts. Please try again.")
            st.stop()
        state["key_concepts"] = key_concepts
        return state

    def summarize_transcript(self, state: QuizState) -> QuizState:
        """Summarizes the lecture transcript with a focus on key educational details."""
        transcription = state["transcription"]
        topic = state["topic"]
        key_concepts = state["key_concepts"]
        system_msg = (
            f"Summarize this {topic} lecture transcript, ensuring that all key concepts are covered. "
            "Structure the summary using clear headings such as 'Introduction', 'Key Concepts', 'Examples', and 'Conclusion'. "
            "Include relevant definitions, explanations, and examples where applicable. "
            "Ignore session logistics, greetings, general chatter, off-topic questions, student joining counts, session breaks, or unrelated discussions. "
            "Ensure the summary is concise, well-organized, and suitable for use as study notes."
        )
        summarized_text = self._call_llm(transcription[:3000], system_msg)
        if not summarized_text:
            st.error("Failed to summarize the transcript. Please try again.")
            st.stop()
        state["summarized_transcript"] = summarized_text
        return state

    def generate_study_notes(self, state: QuizState) -> QuizState:
        """Generates structured, topic-based study notes with clear sections."""
        summarized_text = state["summarized_transcript"]
        system_msg = (
            "Based on the provided summarized transcript, generate detailed and structured study notes. "
            "Organize the notes into the following sections with clear headings:\n"
            "- **Introduction**: Provide an overview of the topic, its relevance, and why it is important.\n"
            "- **Key Concepts**: List and explain the core ideas, methodologies, and terminologies covered in the lecture.\n"
            "- **Definitions**: Include concise definitions of technical terms and concepts discussed.\n"
            "- **Examples**: Provide practical examples or use cases to illustrate the concepts.\n"
            "- **Applications**: Explain how the concepts can be applied in real-world scenarios or industries.\n"
            "- **Tips**: Offer tips, best practices, or common pitfalls to avoid when working with the topic.\n"
            "- **Conclusion**: Summarize the main takeaways and suggest areas for further exploration or study.\n\n"
            "Ensure each section is well-organized and uses bullet points, numbered lists, or step-by-step breakdowns where applicable. "
            "Include practical examples, diagrams (if relevant), and detailed explanations to make the notes comprehensive and easy to follow. "
            "The notes should be suitable for studying purposes and help learners grasp the material effectively."
        )
        study_notes = self._call_llm(summarized_text[:2000], system_msg)
        if not study_notes:
            st.error("Failed to generate study notes. Please try again.")
            st.stop()
        state["study_notes"] = study_notes
        return state

    def question_generator(self, state: QuizState) -> QuizState:
        """Generates multiple-choice quiz questions based on the summarized transcript."""
        summarized_text = state["summarized_transcript"]
        system_msg = f"""
    You are an expert quiz creator. Generate exactly 10 multiple-choice questions (MCQs) based strictly on the following summarized lecture transcript:
    {summarized_text}
    Each question must follow this format **exactly**:
    Question: [Your question]
    A) [Option A]
    B) [Option B]
    C) [Option C]
    D) [Option D]
    Answer: [Correct answer letter, e.g., A]
    Explanation: [Detailed explanation of why the correct answer is correct and why the other options are incorrect]
    Separate each QnA pair with "#####".
    Ensure the questions cover a variety of topics and difficulty levels, including conceptual understanding, application-based scenarios, and problem-solving.
    avoid questions like what is the purpose of the lecture, what is the primary focus of the lecture in context to the course,  What is the purpose of using examples and comparisons between different techniques in the lecture, etc.
    """
        questions_text = self._call_llm(summarized_text[:2000], system_msg)
        blocks = questions_text.split("#####")
        parsed_questions = []
        pattern = re.compile(
            r"Question:\s*(.+?)\n"
            r"A\)\s*(.+?)\n"
            r"B\)\s*(.+?)\n"
            r"C\)\s*(.+?)\n"
            r"D\)\s*(.+?)\n"
            r"Answer:\s*([A-D])\n"
            r"Explanation:\s*(.+)",
            re.DOTALL | re.IGNORECASE
        )
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            match = pattern.search(block)
            if match:
                question, a, b, c, d, answer, explanation = [x.strip() for x in match.groups()]
                parsed_questions.append({
                    "question": question,
                    "options": [f"A) {a}", f"B) {b}", f"C) {c}", f"D) {d}"],
                    "answer": answer,
                    "explanation": explanation
                })
            else:
                st.warning(f"Skipping improperly formatted question block:\n{block}")
        if not parsed_questions:
            st.error("No valid quiz questions were generated. Please check the LLM response format.")
            st.stop()
        state["questions"] = parsed_questions
        return state

# ---- LangGraph Workflow ----
class QuizWorkflow:
    def __init__(self, agents):
        self.agents = agents
        self.workflow = StateGraph(QuizState)
        # Add nodes in processing order
        self.workflow.add_node("classify_topic", agents.classify_topic)
        self.workflow.add_node("extract_key_concepts", agents.extract_key_concepts)
        self.workflow.add_node("summarize_transcript", agents.summarize_transcript)
        self.workflow.add_node("generate_study_notes", agents.generate_study_notes)
        self.workflow.add_node("generate_questions", agents.question_generator)
        # Build workflow chain
        self.workflow.add_edge("classify_topic", "extract_key_concepts")
        self.workflow.add_edge("extract_key_concepts", "summarize_transcript")
        self.workflow.add_edge("summarize_transcript", "generate_study_notes")
        self.workflow.add_edge("generate_study_notes", "generate_questions")
        self.workflow.set_entry_point("classify_topic")
        self.workflow.set_finish_point("generate_questions")
        self.chain = self.workflow.compile()

    def run(self, transcription):
        """Executes the full workflow on the provided transcription."""
        inputs = {"transcription": transcription}
        result = self.chain.invoke(inputs)
        if not result.get("questions"):
            st.error("Workflow failed to generate quiz questions. Please try again.")
            st.stop()
        return result

# ---- Streamlit UI ----
st.title("AI-Powered Quiz & Study Notes Generator")

if transcript_file:
    transcription = transcript_file.read().decode("utf-8")
else:
    transcription = None

if transcription:
    with st.expander("Original Transcription"):
        st.text_area("Transcript", transcription, height=200, label_visibility="collapsed")

if st.button("Generate Study Notes & Quiz"):
    if transcription:
        with st.spinner("Processing..."):
            st.write("Analyzing transcript & generating content...")
            result = QuizWorkflow(QuizAgents()).run(transcription)
            st.session_state.study_notes = result.get("study_notes", "")
            st.session_state.qna_bank = result.get("questions", [])
            st.session_state.user_answers = {}
            st.session_state.show_quiz = False
            st.session_state.topic = result.get("topic", "")
            st.session_state.key_concepts = result.get("key_concepts", "")
    else:
        st.error("Please upload a transcript file first.")

# ---- Display Study Notes ----
if st.session_state.study_notes:
    st.subheader("📚 Generated Study Notes")
    st.markdown(st.session_state.study_notes)
    if st.session_state.topic:
        st.subheader("🔍 Key Concepts")
        st.markdown(st.session_state.key_concepts)
    pdf_study_notes = create_pdf(
        clean_markdown(st.session_state.study_notes + "\n\nKey Concepts:\n" + st.session_state.key_concepts),
        "Study Notes"
    )
    st.download_button("Download Study Notes (PDF)", data=pdf_study_notes, file_name="study_notes.pdf", mime="application/pdf")
    
    # Start Quiz Button
    if st.sidebar.button("Start Quiz"):
        st.session_state.show_quiz = True

# ---- Display Quiz ----
if st.session_state.show_quiz and st.session_state.qna_bank:
    st.subheader("📝 Generated Quiz")
    for i, qna in enumerate(st.session_state.qna_bank):
        with st.container():
            st.markdown(f"**{i+1}. {qna['question']}**")
            st.session_state.user_answers[i] = st.radio(
                f"Select an option for Q{i+1}",
                qna["options"],
                index=None,
                key=f"q_{i}"
            )
            with st.expander("See explanation"):
                st.markdown(f"**Correct Answer:** {qna['answer']}")
                st.text_area("Explanation", qna['explanation'], height=100, key=f"exp_{i}")
    if st.button("Submit Quiz"):
        total_score = sum(
            1 for i, qna in enumerate(st.session_state.qna_bank)
            if st.session_state.user_answers.get(i, "").startswith(qna["answer"])
        )
        st.success(f"Your total score: {total_score}/{len(st.session_state.qna_bank)}")
    quiz_text = ""
    for i, qna in enumerate(st.session_state.qna_bank):
        quiz_text += f"Q{i+1}: {qna['question']}\n"
        quiz_text += "\n".join(qna["options"]) + "\n"
        quiz_text += f"Answer: {qna['answer']}\n"
        quiz_text += f"Explanation: {qna['explanation']}\n\n"
    pdf_quiz = create_pdf(quiz_text, "Quiz")
    st.download_button("Download Quiz (PDF)", data=pdf_quiz, file_name="generated_quiz.pdf", mime="application/pdf")
