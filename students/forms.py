from django import forms

from .models import Candidate, Student


class CandidateForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = [
            "full_name", "email", "phone", "position", "years_experience",
            "skills", "status", "resume", "interview_date", "interview_notes",
        ]
        widgets = {
            "skills": forms.Textarea(attrs={"rows": 3}),
            "interview_date": forms.DateInput(attrs={"type": "date"}),
            "interview_notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
        self.fields["resume"].widget.attrs["accept"] = ".pdf,.doc,.docx"

    def clean_resume(self):
        resume = self.cleaned_data.get("resume")
        if not resume:
            return resume
        if resume.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Resume must be 10 MB or smaller.")
        if not resume.name.lower().endswith((".pdf", ".doc", ".docx")):
            raise forms.ValidationError("Upload a PDF, DOC, or DOCX resume.")
        return resume


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["roll_number", "full_name", "email", "phone", "department",
                  "class_name", "marks", "attendance", "fees_paid"]
        labels = {"class_name": "Class", "fees_paid": "Fees paid"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = "form-check-input" if name == "fees_paid" else "form-control"
        self.fields["roll_number"].error_messages["unique"] = (
            "A student with this roll number already exists.")


class StudentImportForm(forms.Form):
    SUPPORTED_FILE_TYPES = (".xlsx", ".csv", ".pdf", ".docx", ".txt", ".md", ".json")

    file = forms.FileField(label="Student details file", widget=forms.ClearableFileInput(attrs={
        "class": "form-control", "accept": ", ".join(SUPPORTED_FILE_TYPES),
    }))

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(self.SUPPORTED_FILE_TYPES):
            raise forms.ValidationError(
                "Upload an XLSX, CSV, PDF, DOCX, TXT, MD, or JSON file.")
        if f.size > 10 * 1024 * 1024:
            raise forms.ValidationError("File must be 10 MB or smaller.")
        return f


class AskAIForm(forms.Form):
    SUPPORTED_DOCUMENT_TYPES = (
        ".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".html", ".xml", ".xlsx",
    )

    question = forms.CharField(required=False, max_length=300, widget=forms.Textarea(attrs={
        "rows": 2, "class": "form-control",
        "placeholder": "e.g. Find Python developers with 3+ years of experience"}))
    document = forms.FileField(required=False, widget=forms.ClearableFileInput(attrs={
        "class": "form-control", "accept": ", ".join(SUPPORTED_DOCUMENT_TYPES),
    }))

    def clean_document(self):
        document = self.cleaned_data.get("document")
        if not document:
            return document
        if document.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Document must be 10 MB or smaller.")
        if not document.name.lower().endswith(self.SUPPORTED_DOCUMENT_TYPES):
            raise forms.ValidationError(
                "Upload a PDF, DOCX, TXT, MD, CSV, JSON, HTML, XML, or XLSX document.")
        return document

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("question") and not cleaned_data.get("document"):
            raise forms.ValidationError("Enter a question or attach a document.")
        return cleaned_data