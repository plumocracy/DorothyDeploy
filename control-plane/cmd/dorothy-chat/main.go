package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"strings"

	"dorothydeploy/control-plane/internal/api"
	"dorothydeploy/control-plane/internal/controlplane"
)

func main() {
	if err := api.LoadDotEnv(".env"); err != nil {
		log.Fatalf("load .env: %v", err)
	}

	clusterName := flag.String("cluster-name", "dorothy-mvp", "kind cluster name")
	model := flag.String("model", "deepseek/deepseek-v3.2", "OpenRouter model")
	recreateCluster := flag.Bool("recreate-cluster", false, "delete and recreate the kind cluster before sending the message")
	printJSON := flag.Bool("json", false, "print the full JSON response")
	flag.Parse()

	message := strings.Join(flag.Args(), " ")
	if strings.TrimSpace(message) == "" {
		writeError("message is required")
		os.Exit(1)
	}

	cp, err := controlplane.New(controlplane.Options{
		ClusterName:     *clusterName,
		Model:           *model,
		RecreateCluster: *recreateCluster,
	})
	if err != nil {
		writeError(err.Error())
		os.Exit(1)
	}

	response, err := cp.SendMessage(context.Background(), message)
	if err != nil {
		writeError(err.Error())
		os.Exit(1)
	}

	if *printJSON {
		encoded, _ := json.MarshalIndent(response, "", "  ")
		fmt.Println(string(encoded))
		return
	}

	reply, ok := response["reply"].(string)
	if !ok {
		encoded, _ := json.Marshal(response)
		fmt.Println(string(encoded))
		return
	}
	fmt.Println(reply)
}

func writeError(message string) {
	encoded, _ := json.MarshalIndent(map[string]any{"ok": false, "error": message}, "", "  ")
	fmt.Println(string(encoded))
}
