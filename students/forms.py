from django import forms

from .models import Candidate, Student


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            "roll_number", "full_name", "email", "phone", "department",
            "class_name", "marks", "attendance", "fees_paid",
        ]
        labels = {"class_name": "Class", "fees_paid": "Fees paid"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = (
                "form-check-input" if name == "fees_paid" else "form-control"
            )
        self.fields["roll_number"].error_messages["unique"] = (
            "A student with this roll number already exists."
        )


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


class RecordImportForm(forms.Form):
    file = forms.FileField(
        label="Details file",
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": ".csv,.xlsx",
        }),
    )

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]
        if not uploaded_file.name.lower().endswith((".csv", ".xlsx")):
            raise forms.ValidationError("Upload a CSV or XLSX file.")
        if uploaded_file.size > 10 * 1024 * 1024:
            raise forms.ValidationError("File must be 10 MB or smaller.")
        return uploaded_file


class AskAIForm(forms.Form):
    SUPPORTED_DOCUMENT_TYPES = (
        ".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".html", ".xml", ".xlsx",
    )

    question = forms.CharField(
        required=False,
        max_length=4000,
        widget=forms.Textarea(attrs={
            "rows": 4,
            "class": "form-control",
            "placeholder": "Ask OpenAI anything, or ask about an attached document",
        }),
    )
    document = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": ", ".join(SUPPORTED_DOCUMENT_TYPES),
        }),
    )

    def clean_document(self):
        document = self.cleaned_data.get("document")
        if not document:
            return document
        if document.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Document must be 10 MB or smaller.")
        if not document.name.lower().endswith(self.SUPPORTED_DOCUMENT_TYPES):
            raise forms.ValidationError(
                "Upload a PDF, DOCX, TXT, MD, CSV, JSON, HTML, XML, or XLSX document."
            )
        return document

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("question") and not cleaned_data.get("document"):
            raise forms.ValidationError("Enter a question or attach a document.")
        return cleaned_data
