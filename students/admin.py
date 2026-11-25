from django.contrib import admin

from .models import Candidate, Student


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("full_name", "position", "years_experience", "status",
                    "interview_date", "updated_at")
    search_fields = ("full_name", "email", "phone", "position", "skills")
    list_filter = ("status", "position")


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("roll_number", "full_name", "department", "class_name",
                    "marks", "attendance", "fees_paid")
    search_fields = ("roll_number", "full_name", "department", "class_name")
    list_filter = ("department", "fees_paid")