// Reports use the dashboard's canonical adjusted-volume calculation.
import {readFileSync} from 'node:fs';
import {adjustedVolumeSets} from '../web/static/model.mjs';

const data = JSON.parse(readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(adjustedVolumeSets(
  data.sets, data.recovery || [], data.volumeSettings || {},
)));
