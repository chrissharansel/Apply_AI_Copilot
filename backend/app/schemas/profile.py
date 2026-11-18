from pydantic import BaseModel


class Education(BaseModel):
    degree: str = ""
    institution: str = ""
    graduation_year: str = ""


class Employment(BaseModel):
    company: str = ""
    title: str = ""
    start_date: str = ""
    end_date: str = ""        # empty / "Present" = current job
    description: str = ""


class Certification(BaseModel):
    name: str = ""
    issuer: str = ""


class Project(BaseModel):
    name: str = ""
    description: str = ""
    technologies: list[str] = []


class ProfileData(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    current_designation: str = ""
    total_experience_years: float | None = None
    education: list[Education] = []
    employment: list[Employment] = []
    skills: list[str] = []
    certifications: list[Certification] = []
    projects: list[Project] = []
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    desired_role: str = ""
    preferred_locations: list[str] = []
    expected_salary: str = ""
    employment_type: str = ""
    notice_period: str = ""
    work_authorization: str = ""
    availability: str = ""


class ProfileUpdate(BaseModel):
    data: ProfileData
    confirm: bool = False
