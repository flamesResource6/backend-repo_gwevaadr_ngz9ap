import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Post as PostSchema, Comment as CommentSchema, Vote as VoteSchema

app = FastAPI(title="VibeHunt API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utilities

def to_str_id(doc: dict):
    d = doc.copy()
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    # convert datetime to iso
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d

# Models for requests
class PostCreate(BaseModel):
    title: str
    description: str
    link: Optional[str] = None
    tags: List[str] = []
    author_name: Optional[str] = None

class CommentCreate(BaseModel):
    post_id: str
    content: str
    author_name: Optional[str] = None

class VoteToggle(BaseModel):
    post_id: str
    client_id: str

# Seeding demo data if empty

def seed_demo():
    if db is None:
        return
    if db["post"].count_documents({}) > 0:
        return
    demo_posts = [
        {
            "title": "AI Thumbnail Wizard",
            "description": "Auto-generate YouTube thumbnails that actually get clicks using vibe-based prompts.",
            "tags": ["AI", "Creator", "SaaS"],
            "link": "https://ai-thumb-wizard.dev",
            "author_name": "Nova",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
        {
            "title": "Tweet-to-Course",
            "description": "Turn a viral tweet thread into a paid micro-course with landing page in minutes.",
            "tags": ["Education", "NoCode"],
            "link": None,
            "author_name": "Ray",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
        {
            "title": "Adless News",
            "description": "A clean daily tech digest with zero ads. Monetize via pro insights.",
            "tags": ["Media", "Subscription"],
            "link": "https://adless.news",
            "author_name": "Sage",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
        {
            "title": "Cold DM Crafter",
            "description": "Personalized outreach messages that feel human and get replies.",
            "tags": ["Sales", "AI"],
            "link": None,
            "author_name": "Ivy",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
    ]
    result = db["post"].insert_many(demo_posts)
    post_ids = result.inserted_ids
    # seed some votes and comments
    demo_comments = []
    demo_votes = []
    for i, pid in enumerate(post_ids):
        for j in range(i + 1):
            demo_votes.append({
                "post_id": str(pid),
                "client_id": f"seed-client-{j}",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })
        demo_comments.append({
            "post_id": str(pid),
            "author_name": "Guest",
            "content": "Love this!",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
    if demo_votes:
        db["vote"].insert_many(demo_votes)
    if demo_comments:
        db["comment"].insert_many(demo_comments)

seed_demo()

@app.get("/")
def root():
    return {"message": "VibeHunt API running"}

@app.get("/api/posts")
def list_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(8, ge=1, le=50),
    timeframe: Literal["week", "month", "all"] = Query("all"),
    sort_by: Literal["votes", "comments", "latest"] = Query("votes"),
):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    filter_q = {}
    if timeframe != "all":
        now = datetime.now(timezone.utc)
        if timeframe == "week":
            since = now - timedelta(days=7)
        else:
            since = now - timedelta(days=30)
        filter_q["created_at"] = {"$gte": since}

    # Aggregation to compute counts
    pipeline = [
        {"$match": filter_q},
        {
            "$lookup": {
                "from": "vote",
                "localField": "_id",
                "foreignField": "post_id",
                "as": "votes_docs",
                "let": {"pid": {"$toString": "$_id"}},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$post_id", {"$toString": "$$pid"}]}}}
                ],
            }
        },
        {
            "$lookup": {
                "from": "comment",
                "localField": "_id",
                "foreignField": "post_id",
                "as": "comments_docs",
                "let": {"pid": {"$toString": "$_id"}},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$post_id", {"$toString": "$$pid"}]}}}
                ],
            }
        },
        {
            "$addFields": {
                "votes_count": {"$size": "$votes_docs"},
                "comments_count": {"$size": "$comments_docs"},
            }
        },
    ]

    if sort_by == "votes":
        pipeline.append({"$sort": {"votes_count": -1, "created_at": -1}})
    elif sort_by == "comments":
        pipeline.append({"$sort": {"comments_count": -1, "created_at": -1}})
    else:
        pipeline.append({"$sort": {"created_at": -1}})

    pipeline.extend([
        {"$skip": (page - 1) * page_size},
        {"$limit": page_size},
    ])

    items = list(db["post"].aggregate(pipeline))
    items = [to_str_id(x) for x in items]

    total = db["post"].count_documents(filter_q)
    return {"items": items, "total": total, "page": page, "page_size": page_size}

@app.post("/api/posts")
def create_post(payload: PostCreate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    post = PostSchema(**payload.model_dump())
    post_id = create_document("post", post)
    return {"id": post_id}

@app.post("/api/comments")
def add_comment(payload: CommentCreate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    # validate post exists
    try:
        _ = db["post"].find_one({"_id": ObjectId(payload.post_id)})
    except Exception:
        _ = None
    if not _:
        raise HTTPException(status_code=404, detail="Post not found")
    comment = CommentSchema(**payload.model_dump())
    cid = create_document("comment", comment)
    return {"id": cid}

@app.post("/api/vote/toggle")
def toggle_vote(payload: VoteToggle):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    # validate post exists
    try:
        _ = db["post"].find_one({"_id": ObjectId(payload.post_id)})
    except Exception:
        _ = None
    if not _:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = db["vote"].find_one({"post_id": payload.post_id, "client_id": payload.client_id})
    if existing:
        db["vote"].delete_one({"_id": existing["_id"]})
        return {"status": "unvoted"}
    vote = VoteSchema(**payload.model_dump())
    _id = create_document("vote", vote)
    return {"status": "voted", "id": _id}

@app.get("/api/comments/{post_id}")
def list_comments(post_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    items = get_documents("comment", {"post_id": post_id})
    items = [to_str_id(x) for x in items]
    return {"items": items}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
