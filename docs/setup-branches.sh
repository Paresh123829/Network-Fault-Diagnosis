# Git Branches for Team Collaboration
#
# Run these commands after cloning to set up your feature branch.
# Each member works on their own branch and merges to develop.

# Create and push all feature branches
git checkout -b develop
git push -u origin develop

git checkout -b feat/member1-network-data
git push -u origin feat/member1-network-data

git checkout develop

git checkout -b feat/member2-topology-rag
git push -u origin feat/member2-topology-rag

git checkout develop

git checkout -b feat/member3-ai-safety
git push -u origin feat/member3-ai-safety

git checkout develop

git checkout -b feat/member4-platform-ui
git push -u origin feat/member4-platform-ui

git checkout develop

echo "All branches created."
