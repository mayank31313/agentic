---
name: user_profile_manager
description: >-
  Manages the user's personal profile information stored in the workspace's root `user.md` file. Use this skill when a user asks to read, update, or query their personal settings, preferences, or information stored in `user.md`. Trigger phrases include: "Manage my profile", "Get my preferences", "Update user settings", or "Show my profile info".
license: MIT
metadata:
  author: skill_creator
  purpose: user_data_management
compatibility:
  - Requires a FilesystemBackend or Sandbox Backend to perform read/write operations on workspace files.
  - Assumes the existence of a file named `user.md` in the workspace root directory.
---

# User Profile Manager

This skill provides the agent with the capability to securely read, write, and query the user's personal profile information, which is persistently stored in the `user.md` file located at the workspace root.

## Core Functions

The skill exposes three primary functions to interact with the user profile data:

### 1. Read User Profile Content
**Purpose**: To retrieve the entire content of the `user.md` file.
**Input**: None required.
**Output**: The complete content of `user.md` as a string.
**Procedure**:
1.  Access the filesystem path to `user.md` in the workspace root.
2.  Read the entire content of the file.
3.  Return the content to the agent for processing.
**When to Use**: When the agent needs a complete overview of the user's current profile settings.

### 2. Update User Profile Content
**Purpose**: To write new or updated user information to the `user.md` file.
**Input**: A dictionary or structured data object containing the profile fields to update (e.g., `{"preferred_color": "blue", "theme": "dark"}`).
**Output**: A confirmation message indicating successful write operation.
**Procedure**:
1.  Receive the input data structure from the agent.
2.  Parse the input data to ensure it conforms to the expected structure (e.g., valid keys).
3.  Read the existing content of `user.md`.
4.  Apply the provided updates to the existing content (e.g., replacing existing keys or adding new ones).
5.  Write the modified content back to `user.md`, overwriting the previous content.
**When to Use**: When the user provides new information or settings that need to be persisted.

### 3. Query Specific Profile Information
**Purpose**: To retrieve a specific piece of information from `user.md` based on a natural language query.
**Input**: A natural language query string (e.g., "What is my preferred color?", "What is my theme?").
**Output**: The specific value corresponding to the query, or a message stating the information is not found.
**Procedure**:
1.  Receive the natural language query.
2.  Read the entire content of `user.md`.
3.  Analyze the content to extract the value matching the query (e.g., using regex or simple key-value parsing).
4.  Return the extracted value or an appropriate 'Not Found' response.
**When to Use**: When the agent needs a single, specific data point without reading the entire file.

## Edge Cases and Security Notes

*   **File Not Found**: If `user.md` does not exist when attempting a Read or Update operation, the skill must return a specific error indicating the file is missing.
*   **Invalid Update Data**: If the data provided for an Update operation is malformed (e.g., contains unparseable data), the skill must halt the write operation and return an error detailing the schema mismatch.
*   **Security**: File access must be strictly limited to reading/writing `user.md`. No other files in the workspace root should be accessed unless explicitly required by a subsequent step. This skill relies on the backend's security guarantees for filesystem operations.

## Supporting Resources

No supporting files are required for this basic implementation. All logic is contained within the main `SKILL.md`.