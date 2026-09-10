import { Config } from "@remotion/cli/config";

// As imagens e o audio de cada video vivem em videos/<video_id>/, e o Python
// passa esse diretorio com --public-dir na hora de renderizar. Ver ADR 0001.
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setChromiumOpenGlRenderer("angle");
