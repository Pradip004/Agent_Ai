from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver


class Candidate(models.Model):
    class ApplicationStatus(models.TextChoices):
        NEW = "new", "New"
        SCREENING = "screening", "Screening"
        INTERVIEW = "interview", "Interview"
        OFFER = "offer", "Offer"
        HIRED = "hired", "Hired"
        REJECTED = "rejected", "Rejected"

    full_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    position = models.CharField(max_length=120)
    years_experience = models.DecimalField(
        max_digits=4, decimal_places=1, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(60)])
    skills = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=ApplicationStatus.choices,
        default=ApplicationStatus.NEW)
    resume = models.FileField(upload_to="candidate_resumes/", blank=True)
    interview_date = models.DateField(null=True, blank=True)
    interview_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "full_name"]

    def save(self, *args, **kwargs):
        previous_resume = None
        if self.pk:
            previous_resume = type(self).objects.filter(pk=self.pk).values_list(
                "resume", flat=True).first()
        super().save(*args, **kwargs)
        if previous_resume and previous_resume != self.resume.name:
            self._meta.get_field("resume").storage.delete(previous_resume)

    def __str__(self):
        return f"{self.full_name} - {self.position}"


@receiver(post_delete, sender=Candidate)
def delete_candidate_resume(sender, instance, **kwargs):
    if instance.resume:
        instance.resume.delete(save=False)


class Student(models.Model):
    roll_number = models.CharField(max_length=30, unique=True)
    full_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    department = models.CharField(max_length=80)
    class_name = models.CharField(max_length=40, blank=True)
    marks = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                validators=[MinValueValidator(0), MaxValueValidator(100)])
    attendance = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                     validators=[MinValueValidator(0), MaxValueValidator(100)])
    fees_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["roll_number"]

    def __str__(self):
        return f"{self.roll_number} - {self.full_name}"