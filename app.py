from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from pathlib import Path
import uuid

from screening import analyze_resume
from database import (
    initialize_database,
    save_candidate,
    get_all_candidates,
    get_statistics,
    clear_history,
)

from flask import send_from_directory

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"

app = Flask(__name__)
app.secret_key = "resume-screening-demo-key"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

UPLOAD_FOLDER.mkdir(exist_ok=True)

initialize_database()


def extract_text_from_pdf(file_path):
    reader = PdfReader(str(file_path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        job_description = request.form.get("job_description", "").strip()
        resumes = request.files.getlist("resumes")

        valid_files = [
            resume for resume in resumes
            if resume and resume.filename
        ]

        if not job_description:
            flash("Please enter a Job Description.", "error")
            return redirect(url_for("index"))

        if not valid_files:
            flash("Please select at least one PDF resume.", "error")
            return redirect(url_for("index"))

        results = []
        skipped = []

        for resume in valid_files:
            original_filename = secure_filename(resume.filename)

            if not original_filename.lower().endswith(".pdf"):
                skipped.append(original_filename)
                continue

            unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
            file_path = UPLOAD_FOLDER / unique_filename
            resume.save(file_path)

            try:
                resume_text = extract_text_from_pdf(file_path)

                if not resume_text.strip():
                    skipped.append(f"{original_filename} (no readable text)")
                    continue

                analysis = analyze_resume(job_description, resume_text)

                candidate_id = save_candidate(
                    filename=original_filename,
                    job_description=job_description,
                    score=analysis["score"],
                    matched_skills=analysis["matched_skills"],
                    missing_skills=analysis["missing_skills"],
                    skill_score=analysis["skill_score"],
                    similarity_score=analysis["similarity_score"],
                    resume_skills=analysis["resume_skills"],
                )

                results.append({
                    "id": candidate_id,
                    "filename": original_filename,
                    "stored_filename": unique_filename,
                    "score": analysis["score"],
                    "similarity_score": analysis["similarity_score"],
                    "skill_score": analysis["skill_score"],
                    "svm_result": analysis["svm_result"],
                    "svm_confidence": analysis["svm_confidence"],
                    "matched_skills": analysis["matched_skills"],
                    "missing_skills": analysis["missing_skills"],
                    "resume_skills": analysis["resume_skills"],
                    "explanation": analysis["explanation"],
                })

            except Exception as exc:
                skipped.append(f"{original_filename} ({exc})")

        results.sort(key=lambda item: item["score"], reverse=True)

        return render_template(
            "results.html",
            results=results,
            skipped=skipped,
            job_description=job_description,
        )

    return render_template("index.html")

@app.route("/resume/<filename>")
def view_resume(filename):
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename,
        mimetype="application/pdf",
        as_attachment=False
    )


@app.route("/history")
def history():
    candidates = get_all_candidates()
    stats = get_statistics()
    return render_template(
        "history.html",
        candidates=candidates,
        stats=stats,
    )


@app.post("/history/clear")
def clear_history_route():
    clear_history()
    flash("Screening history cleared.", "success")
    return redirect(url_for("history"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
