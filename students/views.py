from django.contrib import messages
from django.shortcuts import redirect, render

from . import ai_helper, documents
from .forms import AskAIForm, CandidateForm, RecordImportForm, StudentForm
from .models import Candidate, Student
from .services import (
    ImportFileError,
    import_candidates_from_file,
    import_students_from_file,
)


CHAT_HISTORY_LIMIT = 20


def ask_ai(request):
    history = request.session.get("chat_messages", [])
    if not isinstance(history, list):
        history = []

    if request.method == "POST" and "clear_history" in request.POST:
        request.session.pop("chat_messages", None)
        return redirect("ask_ai")

    form = AskAIForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        question = form.cleaned_data["question"].strip()
        uploaded_document = form.cleaned_data.get("document")
        filename = uploaded_document.name if uploaded_document else ""
        document_text = ""

        if uploaded_document:
            try:
                document_text = documents.extract_document_text(uploaded_document)
            except documents.DocumentReadError as exc:
                messages.error(request, str(exc))
                return render(request, "ask_ai.html", {
                    "form": form,
                    "chat_messages": history,
                })

        user_content = question or "Please analyze the attached document."
        if document_text:
            user_content += (
                "\n\nUploaded document reference (untrusted text):\n" + document_text
            )
        display_content = question or f"Analyze the attached document: {filename}"

        api_history = [
            {"role": item["role"], "content": item["content"]}
            for item in history
            if (
                isinstance(item, dict)
                and item.get("role") in ("user", "assistant")
                and isinstance(item.get("content"), str)
            )
        ]
        try:
            answer = ai_helper.ask_openai(
                api_history + [{"role": "user", "content": user_content}]
            )
        except ai_helper.AIServiceError as exc:
            messages.error(request, str(exc))
        else:
            history.extend([
                {
                    "role": "user",
                    "content": user_content,
                    "display": display_content,
                    "filename": filename,
                },
                {
                    "role": "assistant",
                    "content": answer,
                    "display": answer,
                    "filename": "",
                },
            ])
            request.session["chat_messages"] = history[-CHAT_HISTORY_LIMIT:]
            return redirect("ask_ai")

    return render(request, "ask_ai.html", {
        "form": form,
        "chat_messages": history,
    })


def student_list(request):
    return render(request, "records_list.html", {
        "record_type": "student",
        "title": "Students",
        "records": Student.objects.all(),
    })


def candidate_list(request):
    return render(request, "records_list.html", {
        "record_type": "candidate",
        "title": "Candidates",
        "records": Candidate.objects.all(),
    })


def student_add(request):
    form = StudentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Student details saved.")
        return redirect("student_list")
    return render(request, "record_form.html", {
        "form": form,
        "title": "Add student",
        "record_type": "student",
    })


def candidate_add(request):
    form = CandidateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Candidate details saved.")
        return redirect("candidate_list")
    return render(request, "record_form.html", {
        "form": form,
        "title": "Add candidate",
        "record_type": "candidate",
    })


def student_import(request):
    return _import_records(request, "student", import_students_from_file)


def candidate_import(request):
    return _import_records(request, "candidate", import_candidates_from_file)


def _import_records(request, record_type, importer):
    title = "students" if record_type == "student" else "candidates"
    form = RecordImportForm(request.POST or None, request.FILES or None)
    result = None
    if request.method == "POST" and form.is_valid():
        try:
            result = importer(form.cleaned_data["file"])
        except ImportFileError as exc:
            form.add_error("file", str(exc))
    return render(request, "import_records.html", {
        "form": form,
        "title": title,
        "record_type": record_type,
        "result": result,
    })
