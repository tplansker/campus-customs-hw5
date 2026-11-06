#!/bin/sh
# Restore the working DB from the untouched original so tickets can be resolved again.
cd "$(dirname "$0")"
cp data/campus_customs.db data/campus_customs_new.db && chmod u+w data/campus_customs_new.db
echo "Reset data/campus_customs_new.db from data/campus_customs.db"
