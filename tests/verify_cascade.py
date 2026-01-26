from sqlalchemy import Column, ForeignKey, Integer, create_engine, event
from sqlmodel import Field, Session, SQLModel, col, select


class Repo(SQLModel, table=True):
    __tablename__ = "repos"
    id: int | None = Field(default=None, primary_key=True)
    name: str


class File(SQLModel, table=True):
    __tablename__ = "files"
    id: int | None = Field(default=None, primary_key=True)
    repo_id: int = Field(sa_column=Column(Integer, ForeignKey("repos.id", ondelete="CASCADE"), nullable=False))
    path: str


class Chunk(SQLModel, table=True):
    __tablename__ = "chunks"
    id: int | None = Field(default=None, primary_key=True)
    file_id: int = Field(sa_column=Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False))
    text: str


engine = create_engine("sqlite:///:memory:")


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SQLModel.metadata.create_all(engine)

with Session(engine) as session:
    repo = Repo(name="test")
    session.add(repo)
    session.commit()
    session.refresh(repo)

    file = File(repo_id=repo.id, path="test.py")
    session.add(file)
    session.commit()
    session.refresh(file)
    assert file.id is not None

    chunk = Chunk(file_id=file.id, text="some code")
    session.add(chunk)
    session.commit()
    session.refresh(chunk)
    assert chunk.id is not None

    print(f"File ID: {file.id}, Chunk ID: {chunk.id}")

    # Delete file via SQL (simulating MetadataStore.delete_file)
    session.exec(select(File).where(col(File.id) == file.id))  # just to ensure loaded
    from sqlalchemy import delete

    session.exec(delete(File).where(col(File.id) == file.id))
    session.commit()

    # Check if chunk is gone
    chunk_exists = session.get(Chunk, chunk.id) is not None
    print(f"Chunk exists after file delete: {chunk_exists}")

    if chunk_exists:
        print("CASCADE FAILED!")
    else:
        print("CASCADE WORKS!")
