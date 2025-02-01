#--------------------------groq cloud ---------------------------------------------

import streamlit as st
import os
import re
import io
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
if api_key:
    client = Groq(api_key=api_key)
else:
    st.sidebar.warning("Please enter your Groq Cloud API key to use the app.")

# ---- Initialize Session State ----
if 'qna_bank' not in st.session_state:
    st.session_state.qna_bank = []
if 'study_notes' not in st.session_state:
    st.session_state.study_notes = ""
if 'user_answers' not in st.session_state:
    st.session_state.user_answers = {}
if 'show_quiz' not in st.session_state:
    st.session_state.show_quiz = False

# ---- Define State Schema ----
class QuizState(TypedDict):
    transcription: str
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
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, txt=title, ln=1, align="C")
    pdf.ln(10)
    pdf.multi_cell(0, 10, content)
    # Use dest="S" to get the PDF as a string, then encode it to bytes.
    pdf_str = pdf.output(dest="S")
    pdf_bytes = pdf_str.encode("latin1")
    return pdf_bytes

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
                model="llama-3.3-70b-versatile",  # Adjust as needed
                temperature=0.5,
                max_tokens=1500
            )
            return response.choices[0].message.content
        except Exception as e:
            st.error(f"API Error: {str(e)}")
            return None

    def summarize_transcript(self, state: QuizState) -> QuizState:
        """Summarizes the lecture transcript to retain key details."""
        transcription = state["transcription"]
        system_msg = (
            "Summarize the provided lecture transcript by extracting the key points. "
            "Retain important details, but remove unnecessary chit-chat, greetings,student joining counts and session logistics."
        )
        summarized_text = self._call_llm(transcription[:3000], system_msg)
        state["summarized_transcript"] = summarized_text
        return state

    def generate_study_notes(self, state: QuizState) -> QuizState:
        """Generates detailed, topic-based structured study notes from the summarized transcript."""
        summarized_text = state["summarized_transcript"]
        system_msg = (
            "Generate detailed, topic-based structured study notes from the following summarized transcript. "
            "Include in-depth explanations, definitions, and examples where appropriate. "
            "Format the notes using headings and bullet points."
        )
        study_notes = self._call_llm(summarized_text[:2000], system_msg)
        state["study_notes"] = study_notes
        return state

    def question_generator(self, state: QuizState) -> QuizState:
        """Generates quiz questions based on the summarized transcript.
           Each QnA pair is separated by the delimiter '#####'."""
        summarized_text = state["summarized_transcript"]
        system_msg = f"""
You are an expert quiz creator. Generate exactly 10 multiple-choice questions (MCQs) based strictly on the following summarized lecture transcript:
{summarized_text}

Each question must follow this format **exactly** (do not include any extra text or headers):

Question: [Your question]
A) [Option A]
B) [Option B]
C) [Option C]
D) [Option D]
Answer: [Correct answer letter, e.g., A]
Explanation: [Brief explanation]

Separate each QnA pair with the delimiter "#####".

For example, your output should look like this:
Question: What is the capital of France?
A) London
B) Berlin
C) Paris
D) Rome
Answer: C
Explanation: Paris is the capital of France.
#####
<Next question...>

Ensure that no additional text is included.
"""
        questions_text = self._call_llm(summarized_text[:2000], system_msg)

        # Debugging: Show raw response from GroqCloud
        st.write("Raw LLM Response for Quiz Generation:")
        #st.code(questions_text)

        # Parse the generated questions
        blocks = questions_text.split("#####")
        parsed_questions = []
        pattern = re.compile(
            r"Question:\s*(.+?)(?:\n|$)"       # Capture question until newline or end
            r".*?A\)\s*(.+?)(?:\n|$)"           # Capture Option A
            r".*?B\)\s*(.+?)(?:\n|$)"           # Capture Option B
            r".*?C\)\s*(.+?)(?:\n|$)"           # Capture Option C
            r".*?D\)\s*(.+?)(?:\n|$)"           # Capture Option D
            r".*?Answer:\s*([A-D])(?:\n|$)"      # Capture Answer letter
            r".*?Explanation:\s*(.+)",          # Capture Explanation until end
            re.DOTALL | re.IGNORECASE
        )
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            m = pattern.search(block)
            if m:
                question, a, b, c, d, answer, explanation = [x.strip() for x in m.groups()]
                parsed_questions.append({
                    "question": question,
                    "options": [f"A) {a}", f"B) {b}", f"C) {c}", f"D) {d}"],
                    "answer": answer,
                    "explanation": explanation
                })
            else:
                st.warning("Skipping block (failed to parse):")
                st.code(block)
        if not parsed_questions:
            st.error("Failed to parse any quiz questions. Check the LLM response format and adjust the prompt or regex accordingly.")
        else:
            st.success("Successfully parsed questions.")
            # Optionally display parsed questions:
            # st.json(parsed_questions)
        state["questions"] = parsed_questions
        return state

# ---- LangGraph Workflow ----
class QuizWorkflow:
    def __init__(self, agents):
        self.agents = agents
        self.workflow = StateGraph(QuizState)
        self.workflow.add_node("summarize_transcript", agents.summarize_transcript)
        self.workflow.add_node("generate_study_notes", agents.generate_study_notes)
        self.workflow.add_node("generate_questions", agents.question_generator)
        self.workflow.add_edge("summarize_transcript", "generate_study_notes")
        self.workflow.add_edge("generate_study_notes", "generate_questions")
        self.workflow.set_entry_point("summarize_transcript")
        self.workflow.set_finish_point("generate_questions")
        self.chain = self.workflow.compile()

    def run(self, transcription):
        """Executes the full workflow on the provided transcription."""
        inputs = {"transcription": transcription}
        return self.chain.invoke(inputs)

# ---- Streamlit UI ----
st.title("AI-Powered Quiz & Study Notes Generator")

# The transcript uploader is now on the sidebar.
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
            st.write("Summarizing transcript & generating content...")
            result = QuizWorkflow(QuizAgents()).run(transcription)
            st.session_state.study_notes = result.get("study_notes", "")
            st.session_state.qna_bank = result.get("questions", [])
            st.session_state.user_answers = {}
            st.session_state.show_quiz = False
    else:
        st.error("Please upload a transcript file first.")

# ---- Display Study Notes ----
if st.session_state.study_notes:
    st.subheader("📚 Generated Study Notes")
    st.markdown(st.session_state.study_notes)
    pdf_study_notes = create_pdf(clean_markdown(st.session_state.study_notes), "Study Notes")
    st.download_button("Download Study Notes (PDF)", data=pdf_study_notes, file_name="study_notes.pdf", mime="application/pdf")

    # Start Quiz Button (placed in sidebar for convenience)
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

















