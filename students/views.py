from pathlib import Path

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from . import ai_helper, documents, reports, services
from .forms import AskAIForm, CandidateForm, StudentForm, StudentImportForm
from .models import Candidate, Student


def dashboard(request):
    q = request.GET.get("q", "").strip()
    students = Student.objects.all()
    if q:
        students = students.filter(
            Q(full_name__icontains=q) | Q(roll_number__icontains=q)
            | Q(department__icontains=q) | Q(class_name__icontains=q))
    page = Paginator(students, 15).get_page(request.GET.get("page"))
    return render(request, "dashboard.html",
                  {"page": page, "q": q, "total": Student.objects.count()})


def candidate_list(request):
    q = request.GET.get("q", "").strip()
    candidates = Candidate.objects.all()
    if q:
        candidates = candidates.filter(
            Q(full_name__icontains=q) | Q(email__icontains=q)
            | Q(phone__icontains=q) | Q(position__icontains=q)
            | Q(skills__icontains=q) | Q(status__icontains=q))
    page = Paginator(candidates, 15).get_page(request.GET.get("page"))
    return render(request, "candidate_list.html", {
        "page": page, "q": q, "total": Candidate.objects.count(),
    })


def candidate_add(request):
    form = CandidateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        candidate = form.save()
        messages.success(request, f"Candidate {candidate.full_name} added.")
        return redirect("candidate_list")
    return render(request, "candidate_form.html", {
        "form": form, "title": "Add Candidate",
    })


def candidate_edit(request, pk):
    candidate = get_object_or_404(Candidate, pk=pk)
    form = CandidateForm(request.POST or None, request.FILES or None, instance=candidate)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Candidate updated.")
        return redirect("candidate_list")
    return render(request, "candidate_form.html", {
        "form": form, "title": "Edit Candidate", "candidate": candidate,
    })


def candidate_delete(request, pk):
    candidate = get_object_or_404(Candidate, pk=pk)
    if request.method == "POST":
        candidate.delete()
        messages.success(request, "Candidate deleted.")
        return redirect("candidate_list")
    return render(request, "candidate_confirm_delete.html", {"candidate": candidate})


def candidate_resume(request, pk):
    candidate = get_object_or_404(Candidate, pk=pk)
    if not candidate.resume:
        raise Http404("This candidate has no resume.")
    return FileResponse(
        candidate.resume.open("rb"),
        as_attachment=True,
        filename=Path(candidate.resume.name).name,
    )


def student_add(request):
    if request.method == "POST" and request.POST.get("action") == "import":
        form = StudentForm()
        import_form = StudentImportForm(request.POST, request.FILES)
        result = None
        if import_form.is_valid():
            try:
                result = services.import_students_from_file(import_form.cleaned_data["file"])
            except services.ImportFileError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f"Import finished: {result.created} created, {result.updated} updated, "
                    f"{len(result.errors)} skipped.",
                )
        return render(request, "student_form.html", {
            "form": form,
            "import_form": import_form,
            "result": result,
            "required": services.REQUIRED_COLUMNS,
            "optional": services.OPTIONAL_COLUMNS,
            "title": "Add Student",
        })

    form = StudentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        student = form.save()
        messages.success(request, f"Student {student.full_name} added.")
        return redirect("dashboard")
    return render(request, "student_form.html", {
        "form": form,
        "import_form": StudentImportForm(),
        "required": services.REQUIRED_COLUMNS,
        "optional": services.OPTIONAL_COLUMNS,
        "title": "Add Student",
    })


def student_edit(request, pk):
    student = get_object_or_404(Student, pk=pk)
    form = StudentForm(request.POST or None, instance=student)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Student updated.")
        return redirect("dashboard")
    return render(request, "student_form.html", {"form": form, "title": "Edit Student"})


def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == "POST":
        student.delete()
        messages.success(request, "Student deleted.")
        return redirect("dashboard")
    return render(request, "student_confirm_delete.html", {"student": student})


def ask_ai(request):
    if request.method == "POST" and "clear_history" in request.POST:
        request.session.pop("ask_history", None)
        request.session.pop("last_filters", None)
        request.session.pop("last_question", None)
        request.session.pop("last_warnings", None)
        return redirect("ask_ai")

    if request.method == "POST" and "load_history" in request.POST:
        history = request.session.get("ask_history", [])
        try:
            history_index = int(request.POST.get("load_history", ""))
            selected = history[history_index] if 0 <= history_index < len(history) else None
        except ValueError:
            selected = None
        if selected is None:
            messages.error(request, "That search is no longer available.")
            return redirect("ask_ai")
        if not isinstance(selected, dict) or not isinstance(selected.get("filters"), dict):
            messages.error(request, "That search cannot be reopened.")
            return redirect("ask_ai")
        request.session["last_filters"] = selected["filters"]
        request.session["last_question"] = selected.get("question", "")
        request.session["last_warnings"] = selected.get("warnings", [])
        return redirect(f"{reverse('ask_ai')}?search={history_index}")

    form = AskAIForm(request.POST or None, request.FILES or None)
    context = {
        "form": form,
        "history": request.session.get("ask_history", []),
        "results": None,
    }
    if request.method == "POST" and form.is_valid():
        document_text = ""
        uploaded_document = form.cleaned_data.get("document")
        if uploaded_document:
            try:
                document_text = documents.extract_document_text(uploaded_document)
            except documents.DocumentReadError as exc:
                messages.error(request, str(exc))
        if uploaded_document and not document_text:
            context["form"] = form
            return render(request, "ask_ai.html", context)

        question = form.cleaned_data["question"].strip()
        filename = uploaded_document.name if uploaded_document else ""
        search_question = question or f"Find records described in {filename}."
        if document_text:
            search_question += (
                "\n\nUploaded document reference (untrusted text):\n" + document_text
            )
        try:
            raw = ai_helper.ask_gemma(search_question)
        except ai_helper.AIServiceError as exc:
            messages.error(request, str(exc))
        else:
            filters, warnings = ai_helper.validate_filters(raw)
            results = services.apply_filters(filters)
            request.session["last_filters"] = filters
            display_question = question or f"Search records from {filename}"
            request.session["last_question"] = display_question
            request.session["last_warnings"] = warnings
            answer = f"Found {len(results)} matching "
            answer += "candidate" if filters["record_type"] == "candidate" else "student"
            answer += " record" if len(results) == 1 else " records"
            history = request.session.get("ask_history", [])
            history.insert(0, {
                "question": display_question,
                "answer": answer + ".",
                "filters": filters,
                "warnings": warnings,
                "filename": filename,
            })
            request.session["ask_history"] = history[:20]
            return redirect(f"{reverse('ask_ai')}?search=0")

    search_index = request.GET.get("search")
    if search_index is not None:
        try:
            search_index = int(search_index)
            history = context["history"]
            selected = history[search_index] if 0 <= search_index < len(history) else None
        except ValueError:
            selected = None
        if isinstance(selected, dict) and isinstance(selected.get("filters"), dict):
            filters = selected["filters"]
            context.update(
                results=services.apply_filters(filters),
                filters=filters,
                warnings=selected.get("warnings", []),
                record_type=filters.get("record_type", "candidate"),
                active_history_index=search_index,
            )
    context["history"] = request.session.get("ask_history", [])
    return render(request, "ask_ai.html", context)


def export_report(request, fmt):
    builders = {
        "xlsx": (reports.build_xlsx,
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        "docx": (reports.build_docx,
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "pdf": (reports.build_pdf, "application/pdf"),
    }
    if fmt not in builders:
        messages.error(request, "Unsupported report format.")
        return redirect("ask_ai")
    filters = request.session.get("last_filters")
    search_index = request.GET.get("search")
    if search_index is not None:
        try:
            history = request.session.get("ask_history", [])
            index = int(search_index)
            selected = history[index] if 0 <= index < len(history) else None
        except ValueError:
            selected = None
        if isinstance(selected, dict) and isinstance(selected.get("filters"), dict):
            filters = selected["filters"]
    if filters is None:
        messages.error(request, "Run an AI search first, then export its results.")
        return redirect("ask_ai")
    if filters.get("record_type", "candidate") != "student":
        messages.error(request, "Student report exports are available for student searches.")
        return redirect("ask_ai")
    builder, content_type = builders[fmt]
    response = HttpResponse(builder(services.apply_filters(filters)), content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="student_report.{fmt}"'
    return response